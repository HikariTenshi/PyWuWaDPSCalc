/**
 * Wuwa DPS Calculator Script
 * by @Maygi
 * 
 * This is the script attached to the Wuwa DPS Calculator. Running this is required to update
 * all the calculations.
 */
var sheet = SpreadsheetApp.getActiveSpreadsheet();
var rotationSheet = sheet.getSheetByName('Calculator');
var CHECK_STATS = rotationSheet.getRange('I26').getValue();
var ITERATIVE = rotationSheet.getRange('I27').getValue();

var STANDARD_BUFF_TYPES = ['Normal', 'Heavy', 'Skill', 'Liberation'];
var ELEMENTAL_BUFF_TYPES = ['Glacio', 'Fusion', 'Electro', 'Aero', 'Spectro', 'Havoc'];
var WEAPON_MULTIPLIERS = new Map([
    [1, [1, 1]],
    [20, [2.59, 1.78]],
    [40, [5.03, 2.56]],
    [50, [6.62, 2.94]],
    [60, [8.24, 3.33]],
    [70, [9.47, 3.72]],
    [80, [11.15, 4.11]],
    [90, [12.5, 4.5]]
]);
var CHAR_CONSTANTS = getCharacterConstants();
var skillData = [];
var passiveDamageInstances = [];
var weaponData = {};
var charData = {};
var characters = [];
var sequences = [];
var lastTotalBuffMap = []; //the last updated total buff maps for each character
var bonusStats = [];
var queuedBuffs = [];
var skillLevelMultiplier = rotationSheet.getRange('AH5').getValue();

/**
 * The "Opener" damage is the total damage dealt before the first main DPS (first character) executes their Outro for the first time.
 * 
 */
var openerDamage = 0;
var openerTime = 0;
var loopDamage = 0;
var mode = 'Opener';

var ROTATION_START = 34;
var ROTATION_END = 145;

var jinhsiOutroActive = false;
var rythmicVibrato = 0;

var startFullReso = false;

var res = rotationSheet.getRange('D5').getValue();
var enemyLevel = rotationSheet.getRange('H4').getValue();
var levelCap = rotationSheet.getRange('F4').getValue();

/**
 * Data for stat analysis.
 */
let statCheckMap = new Map([
    ['Attack', .086],
    ['Health', .086],
    ['Defense', .109],
    ['Crit', .081],
    ['Crit Dmg', .162],
    ['Normal', .086],
    ['Heavy', .086],
    ['Skill', .086],
    ['Liberation', .086],
    ['Flat Attack', 40]
]);
var charStatGains = {};
var charEntries = {};
let totalDamageMap = new Map([
    ['Normal', 0],
    ['Heavy', 0],
    ['Skill', 0],
    ['Liberation', 0],
    ['Intro', 0],
    ['Outro', 0],
    ['Echo', 0]
]);
var damageByCharacter = {};

/**
 * The main method that runs all the calculations and updates the data.
 * Yes, I know, it's like an 800 line method, so ugly.
 */
function runCalculations() {
    var character1 = rotationSheet.getRange('B7').getValue();
    var character2 = rotationSheet.getRange('B8').getValue();
    var character3 = rotationSheet.getRange('B9').getValue();
    var levelCap = rotationSheet.getRange('F4').getValue();
    var oldDamage = rotationSheet.getRange('G32').getValue();
    startFullReso = rotationSheet.getRange('D4').getValue();
    var activeBuffs = {};
    let writeBuffsPersonal = [];
    let writeBuffsTeam = [];
    let writeStats = [];
    let writeResonance = [];
    let writeConcerto = [];
    let writeDamage = [];
    let writeDamageNote = [];

    characters = [character1, character2, character3];
    activeBuffs['Team'] = new Set();
    activeBuffs[character1] = new Set();
    activeBuffs[character2] = new Set();
    activeBuffs[character3] = new Set();

    var lastSeen = {};
    rotationSheet.getRange('H26').setValue(oldDamage);

    var initialDCond = {};
    var cooldownMap = new Map();

    charData = {};

    bonusStats = getBonusStats(character1, character2, character3);

    for (var j = 0; j < characters.length; j++) {
        damageByCharacter[characters[j]] = 0;
        charEntries[characters[j]] = 0;
        charStatGains[characters[j]] = {
            'Attack': 0,
            'Health': 0,
            'Defense': 0,
            'Crit': 0,
            'Crit Dmg': 0,
            'Normal': 0,
            'Heavy': 0,
            'Skill': 0,
            'Liberation': 0,
            'Flat Attack': 0
        };
    }
    //console.log(charStatGains);

    weaponData = {};
    var weapons = getWeapons();

    var charactersWeaponsRange = rotationSheet.getRange("D7:D9").getValues();
    var weaponRankRange = rotationSheet.getRange("F7:F9").getValues();

    //load echo data into the echo parameter
    var echoes = getEchoes();

    for (var i = 0; i < characters.length; i++) {
        weaponData[characters[i]] = characterWeapon(weapons[charactersWeaponsRange[i][0]], levelCap, weaponRankRange[i][0]);
        charData[characters[i]] = rowToCharacterInfo(rotationSheet.getRange(`A${7 + i}:Z${7 + i}`).getValues()[0], levelCap);
        sequences[characters[i]] = charData[characters[i]].resonanceChain;

        let echoName = charData[characters[i]].echo;
        charData[characters[i]].echo = echoes[echoName];
        skillData[echoName] = charData[characters[i]].echo;
        console.log(`setting skill data for echo ${echoName}; echo cd is ${charData[characters[i]].echo.cooldown}`);
        initialDCond[characters[i]] = new Map([
            ['Forte', 0],
            ['Concerto', 0],
            ['Resonance', 0]
        ]);
        lastSeen[characters[i]] = -1;
    }
    skillData = [];
    var effectObjects = getSkills();
    effectObjects.forEach(function (effect) {
        skillData[effect.name] = effect;
    });


    //console.log(activeBuffs);
    var trackedBuffs = []; // Stores the active buffs for each time point.
    var dataCellColReso = 'D';
    var dataCellColConcerto = 'E';
    var dataCellCol = 'F';
    var dataCellColTeam = 'G';
    var dataCellColDmg = 'H';
    var dataCellColResults = 'I';
    var dataCellRowResults = ROTATION_END + 3;
    var dataCellColNextSub = 'I';
    var dataCellRowNextSub = 18;
    var dataCellColDCond = 'M';
    var dataCellRowDCond = ROTATION_END + 4;
    var dataCellTime = 'AH';

    /**
     * Outro buffs are special, and are saved to be applied to the NEXT character swapped into.
     */
    var queuedBuffsForNext = [];
    var lastCharacter = null;

    var swapped = false;
    var allBuffs = getActiveEffects(); // retrieves all buffs "in play" from the ActiveEffects table.
    var weaponBuffsRange = sheet.getSheetByName('WeaponBuffs').getRange("A2:K500").getValues().filter(function (row) {
        return row[0].toString().trim() !== ''; // Ensure that the name is not empty
    });
    var weaponBuffData = weaponBuffsRange.map(rowToWeaponBuffRawInfo);

    var echoBuffsRange = sheet.getSheetByName('EchoBuffs').getRange("A2:K500").getValues().filter(function (row) {
        return row[0].toString().trim() !== ''; // Ensure that the name is not empty
    });
    var echoBuffData = echoBuffsRange.map(rowToEchoBuffInfo);

    for (var i = 0; i < 3; i++) { //loop through characters and add buff data if applicable
        echoBuffData.forEach(echoBuff => {
            if (echoBuff.name.includes(charData[characters[i]].echo.name) || echoBuff.name.includes(charData[characters[i]].echo.echoSet)) {
                var newBuff = createEchoBuff(echoBuff, characters[i]);
                allBuffs.push(newBuff);
                console.log("adding echo buff " + echoBuff.name + " to " + characters[i]);
                console.log(newBuff);
            }
        });
        weaponBuffData.forEach(weaponBuff => {
            if (weaponBuff.name.includes(weaponData[characters[i]].weapon.buff)) {
                var newBuff = rowToWeaponBuff(weaponBuff, weaponData[characters[i]].rank, characters[i]);
                console.log("adding weapon buff " + newBuff.name + " to " + characters[i]);
                console.log(newBuff);
                allBuffs.push(newBuff);
            }
        });
    }




    //apply passive buffs
    for (let i = allBuffs.length - 1; i >= 0; i--) {
        let buff = allBuffs[i];
        if (buff.triggeredBy === 'Passive' && buff.duration === 'Passive' && buff.specialCondition == null) {
            if (buff.type === 'StackingBuff') {
                buff.duration = 9999;
                console.log("passive stacking buff " + buff.name + " applies to: " + buff.appliesTo + "; stack interval aka starting stacks: " + buff.stackInterval);
                activeBuffs[buff.appliesTo].add(createActiveStackingBuff(buff, 0, Math.min(buff.stackInterval, buff.stackLimit)));
            } else if (buff.type === 'Buff') {
                buff.duration = 9999;
                console.log("passive buff " + buff.name + " applies to: " + buff.appliesTo);
                activeBuffs[buff.appliesTo].add(createActiveBuff(buff, 0));
                console.log("adding passive buff : " + buff.name + " to " + buff.appliesTo);

                allBuffs.splice(i, 1); // remove passive buffs from the list afterwards
            }
        }
    }

    /**
     * Buff sorting - damage effects need to always be defined first so if other buffs exist that can be procced by them, then they can be added to the "proccable" list.
     * Buffs that have "Buff:" conditions need to be last, as they evaluate the presence of buffs.
     */
    allBuffs.sort((a, b) => {
        // If a.type is "Dmg" and b.type is not, a comes first
        if ((a.type === "Dmg" || a.classifications.includes("Hl")) && (b.type !== "Dmg" || !b.classifications.includes("Hl"))) {
            return -1;
        }
        // If b.type is "Dmg" and a.type is not, b comes first
        else if ((a.type !== "Dmg" || !a.classifications.includes("Hl")) && (b.type === "Dmg" | b.classifications.includes("Hl"))) {
            return 1;
        }
        // If a.triggeredBy contains "Buff:" and b does not, b comes first
        else if (a.triggeredBy.includes("Buff:") && (!b.triggeredBy.includes("Buff:"))) {
            return 1;
        }
        // If b.triggeredBy contains "Buff:" and a does not, a comes first
        else if (!a.triggeredBy.includes("Buff:") && !b.triggeredBy.includes("Buff:")) {
            return -1;
        }
        // Both have the same type or either both are "Dmg" types, or both have the same trigger condition
        // Retain their relative positions
        else {
            return 0;
        }
    });

    console.log("ALL BUFFS:");
    //console.log(allBuffs);
    //console.log(weaponBuffsRange[0]);


    //clear the content
    let rotaRange = rotationSheet.getRange(`D${ROTATION_START}:AH${ROTATION_END}`);

    rotaRange.setValue('');
    rotaRange.setFontWeight('normal');
    rotaRange.clearNote();

    let validationRange = rotationSheet.getRange(`B${ROTATION_START}:C${ROTATION_END}`);
    validationRange.setFontColor(null);
    validationRange.clearNote();

    var statWarningRange = rotationSheet.getRange('I21');
    if (CHECK_STATS) {
        statWarningRange.setValue('The above values are accurate for the latest simulation!')
    } else {
        statWarningRange.setValue('The above values are from a PREVIOUS SIMULATION.')
    }
    var currentTime = 0;
    var liveTime = 0;
    var endLine = ROTATION_END;

    let characterRange = `A${ROTATION_START}:A${ROTATION_END}`;
    let skillRange = `B${ROTATION_START}:B${ROTATION_END}`;
    let timeRange = `C${ROTATION_START}:C${ROTATION_END}`;
    let activeCharacters = rotationSheet.getRange(characterRange).getValues().flat();
    let skills = rotationSheet.getRange(skillRange).getValues().flat();
    let times = rotationSheet.getRange(timeRange).getValues().flat();
    let bonusTimeTotal = 0;

    for (var i = ROTATION_START; i <= ROTATION_END; i++) {
        swapped = false;
        let healFound = false;
        let removeBuff = null;
        let removeBuffInstant = [];
        let passiveDamageQueue = [];
        let passiveDamageQueued = null;
        let activeCharacter = activeCharacters[i - ROTATION_START];
        let bonusTimeCurrent = 0;
        currentTime = times[i - ROTATION_START] + bonusTimeTotal;
        console.log(`new rotation line: ${i}; character: ${activeCharacter}; skill: ${skills[i - ROTATION_START]}; time: ${times[i - ROTATION_START]} + ${bonusTimeTotal}`);


        if (lastCharacter != null && activeCharacter != lastCharacter) { //a swap was performed
            swapped = true;
        }
        let currentSkill = skills[i - ROTATION_START]; // the current skill
        //console.log(`lastSeen for ${activeCharacter}: ${lastSeen[activeCharacter]}. time diff: ${currentTime - lastSeen[activeCharacter]} swapped: ${swapped}`);
        let skillRef = getSkillReference(skillData, currentSkill, activeCharacter);
        if (swapped && (currentTime - lastSeen[activeCharacter]) < 1 && !(skillRef.name.startsWith("Intro") || skillRef.name.startsWith("Outro"))) { //add swap-in time
            let extraToAdd = 1 - (currentTime - lastSeen[activeCharacter]);
            console.log(`adding extra time. current time: ${currentTime}; lastSeen: ${lastSeen[activeCharacter]}; skill: ${skillRef.name}; time to add: ${1 - (currentTime - lastSeen[activeCharacter])}`);
            rotationSheet.getRange(dataCellTime + i).setValue(extraToAdd);
            bonusTimeTotal += extraToAdd;
            bonusTimeCurrent += extraToAdd;
        }
        if (currentSkill.length == 0) {
            endLine = Math.max(ROTATION_START, i - 1);
            break;
        }
        lastSeen[activeCharacter] = currentTime + skillRef.castTime - skillRef.freezeTime;
        let classification = skillRef.classifications;
        if (skillRef.name.includes('Temporal Bender')) {
            jinhsiOutroActive = true; //just for the sake of saving some runtime so we don't have to loop through buffs or passive effects...
        }
        if (skillRef.name.includes("Liberation")) { //reset swap-back timers
            characters.forEach(character => {
                lastSeen[character] = -1;
            });
        }

        if (skillRef.cooldown > 0) {
            let skillName = skillRef.name.split(" (")[0];
            let maxCharges = skillRef.maxCharges || 1;
            if (!cooldownMap.has(skillName)) {
                cooldownMap.set(skillName, { nextValidTime: currentTime, charges: maxCharges, lastUsedTime: currentTime });
            }
            let skillTrack = cooldownMap.get(skillName);
            let elapsed = currentTime - skillTrack.lastUsedTime;
            let restoredCharges = Math.min(
                Math.floor(elapsed / skillRef.cooldown),
                maxCharges - skillTrack.charges
            );
            skillTrack.charges += restoredCharges;
            if (restoredCharges > 0) {
                skillTrack.lastUsedTime += restoredCharges * skillRef.cooldown;
            }
            skillTrack.nextValidTime = skillTrack.lastUsedTime + skillRef.cooldown;
            console.log(`${skillName}: ${skillTrack.charges}, last used: ${skillTrack.lastUsedTime}; restored: ${restoredCharges}; next valid: ${skillTrack.nextValidTime}`);

            if (skillTrack.charges > 0) {
                if (skillTrack.charges == maxCharges) //only update the timer when you're at max stacks to start regenerating the charge
                    skillTrack.lastUsedTime = currentTime;
                skillTrack.charges -= 1;
                cooldownMap.set(skillName, skillTrack);
            } else {
                let nextValidTime = skillTrack.nextValidTime;
                console.log(`not enough charges for skill. next valid time: ${nextValidTime}`);
                if (nextValidTime - currentTime <= 1) { //
                    let delay = nextValidTime - currentTime;
                    rotationSheet.getRange(dataCellTime + i).setValue(Math.max(bonusTimeCurrent, delay));
                    rotationSheet.getRange('C' + (i)).setFontColor('#FF7F50');
                    rotationSheet.getRange('C' + (i)).setNote(`This skill is on cooldown until ${nextValidTime.toFixed(2)}. A waiting time of ${(delay).toFixed(2)} seconds was added to accommodate.`);
                    bonusTimeTotal += delay;
                } else {
                    rotationSheet.getRange('C' + (i)).setFontColor('#ff0000');
                    rotationSheet.getRange('C' + (i)).setNote(`Illegal rotation! This skill is on cooldown until ${nextValidTime.toFixed(2)}`);
                }
                cooldownMap.set(skillName, skillTrack);
            }
        }

        /*console.log("Active Character: " + activeCharacter + "; Current buffs: " + activeBuffs[activeCharacter] +"; filtering for expired");*/

        let activeBuffsArray = [...activeBuffs[activeCharacter]];
        let buffsToRemove = [];
        let buffEnergyItems = [];
        activeBuffsArray = activeBuffsArray.filter(activeBuff => {
            let endTime = ((activeBuff.buff.type === "StackingBuff")
                ? activeBuff.stackTime
                : activeBuff.startTime) + activeBuff.buff.duration;
            //console.log(activeBuff.buff.name + " end time: " + endTime +"; current time = " + currentTime);
            if (activeBuff.buff.type === "BuffUntilSwap" && swapped) {
                console.log("BuffUntilSwap buff " + activeBuff.buff.name + " was removed");
                return false;
            }
            if (currentTime > endTime && activeBuff.buff.name === 'Outro: Temporal Bender')
                jinhsiOutroActive = false;
            if (currentTime > endTime && activeBuff.buff.type === 'ResetBuff') {
                console.log(`resetbuff has triggered: searching for ${activeBuff.buff.classifications} to delete`);
                buffsToRemove.push(activeBuff.buff.classifications);
            }
            if (currentTime > endTime) {
                console.log(`buff ${activeBuff.buff.name} has expired; currentTime=${currentTime}; endTime=${endTime}`)
            }
            return currentTime <= endTime; // Keep the buff if the current time is less than or equal to the end time
        });
        activeBuffs[activeCharacter] = new Set(activeBuffsArray); // Convert the array back into a Set

        for (let classification of buffsToRemove) {
            activeBuffs[activeCharacter] = new Set([...activeBuffs[activeCharacter]].filter(buff => !buff.buff.name.includes(classification)));
            activeBuffs['Team'] = new Set([...activeBuffs['Team']].filter(buff => !buff.buff.name.includes(classification)));
        }
        if (swapped && queuedBuffsForNext.length > 0) { //add outro skills after the buffuntilswap check is performed
            queuedBuffsForNext.forEach(queuedBuff => {
                let found = false;
                let outroCopy = JSON.parse(JSON.stringify(queuedBuff));
                outroCopy.buff.appliesTo = outroCopy.buff.appliesTo === 'Next' ? activeCharacter : outroCopy.buff.appliesTo;
                let activeSet = queuedBuff.buff.appliesTo === 'Team' ? activeBuffs['Team'] : activeBuffs[outroCopy.buff.appliesTo];

                activeSet.forEach(activeBuff => { //loop through and look for if the buff already exists
                    if (activeBuff.buff.name == outroCopy.buff.name && activeBuff.buff.triggeredBy === outroCopy.buff.triggeredBy) {
                        found = true;
                        if (activeBuff.buff.type === 'StackingBuff') {
                            let effectiveInterval = activeBuff.buff.stackInterval;
                            if (activeBuff.buff.name.startsWith('Incandescence') && jinhsiOutroActive) {
                                effectiveInterval = 1;
                            }
                            console.log(`currentTime: ${currentTime}; activeBuff.stackTime: ${activeBuff.stackTime}; effectiveInterval: ${effectiveInterval}`);
                            if (currentTime - activeBuff.stackTime >= effectiveInterval) {
                                console.log(`updating stacks for ${activeBuff.buff.name}: new stacks: ${outroCopy.stacks} + ${activeBuff.stacks}; limit: ${activeBuff.buff.stackLimit}`);
                                activeBuff.stacks = Math.min(activeBuff.stacks + outroCopy.stacks, activeBuff.buff.stackLimit);
                                activeBuff.stackTime = currentTime;
                            }
                        } else {
                            activeBuff.startTime = currentTime;
                            console.log(`updating startTime of ${activeBuff.buff.name} to ${currentTime}`)
                        }
                    }
                });
                if (!found) { //add a new buff
                    activeSet.add(outroCopy);
                    console.log("adding new buff from queuedBuffForNext: " + outroCopy.buff.name + " x" + outroCopy.stacks);
                }

                console.log("Added queuedForNext buff [" + queuedBuff.buff.name + "] from " + lastCharacter + " to " + activeCharacter);
                console.log(outroCopy);
            });
            queuedBuffsForNext = [];
        }
        lastCharacter = activeCharacter;
        if (queuedBuffs.length > 0) { //add queued buffs procced from passive effects
            queuedBuffs.forEach(queuedBuff => {
                let found = false;
                let copy = JSON.parse(JSON.stringify(queuedBuff));
                copy.buff.appliesTo = (copy.buff.appliesTo === 'Next' || copy.buff.appliesTo === 'Active') ? activeCharacter : copy.buff.appliesTo;
                let activeSet = copy.buff.appliesTo === 'Team' ? activeBuffs['Team'] : activeBuffs[copy.buff.appliesTo];

                console.log("Processing queued buff [" + queuedBuff.buff.name + "]; applies to " + copy.buff.appliesTo);
                if (queuedBuff.buff.type.includes('ConsumeBuff')) { //a queued consumebuff will instantly remove said buffs
                    removeBuffInstant.push(copy.buff.classifications);
                } else {
                    activeSet.forEach(activeBuff => { //loop through and look for if the buff already exists
                        if (activeBuff.buff.name == copy.buff.name && activeBuff.buff.triggeredBy === copy.buff.triggeredBy) {
                            found = true;
                            if (activeBuff.buff.type === 'StackingBuff') {
                                let effectiveInterval = activeBuff.buff.stackInterval;
                                if (activeBuff.buff.name.startsWith('Incandescence') && jinhsiOutroActive) {
                                    effectiveInterval = 1;
                                }
                                console.log(`currentTime: ${currentTime}; activeBuff.stackTime: ${activeBuff.stackTime}; effectiveInterval: ${effectiveInterval}`);
                                if (currentTime - activeBuff.stackTime >= effectiveInterval) {
                                    activeBuff.stackTime = copy.startTime; // we already calculated the start time based on lastProc
                                    console.log(`updating stacks for ${activeBuff.buff.name}: new stacks: ${copy.stacks} + ${activeBuff.stacks}; limit: ${activeBuff.buff.stackLimit}; time: ${activeBuff.stackTime}`);
                                    activeBuff.stacks = Math.min(activeBuff.stacks + copy.stacks, activeBuff.buff.stackLimit);
                                    activeBuff.stackTime = currentTime; // this actually is not accurate, will fix later. should move forward on multihits
                                }
                            } else {
                                // sometimes a passive instance-triggered effect that procced earlier gets processed later. 
                                // to work around this, check which activated effect procced later
                                if (copy.startTime > activeBuff.startTime) {
                                    activeBuff.startTime = copy.startTime;
                                    console.log(`updating startTime of ${activeBuff.buff.name} to ${copy.startTime}`)
                                }
                            }
                        }
                    });
                    if (!found) { //add a new buff
                        //copy.startTime = currentTime;
                        activeSet.add(copy);
                        console.log("adding new buff from queue: " + copy.buff.name + " x" + copy.stacks + " at " + copy.startTime);
                    }
                }
            });
            queuedBuffs = [];
        }

        let activeBuffsArrayTeam = [...activeBuffs['Team']];
        activeBuffsArrayTeam = activeBuffsArrayTeam.filter(activeBuff => {
            let endTime = ((activeBuff.buff.type === "StackingBuff")
                ? activeBuff.stackTime
                : activeBuff.startTime) + activeBuff.buff.duration;
            //console.log("current teambuff end time: " + endTime +"; current time = " + currentTime);
            return currentTime <= endTime; // Keep the buff if the current time is less than or equal to the end time
        });
        activeBuffs['Team'] = new Set(activeBuffsArrayTeam); // Convert the array back into a Set

        // check for new buffs triggered at this time and add them to the active list
        allBuffs.forEach(buff => {
            //console.log(buff);
            let activeSet = buff.appliesTo === 'Team' ? activeBuffs['Team'] : activeBuffs[activeCharacter];
            let triggeredBy = buff.triggeredBy;
            if (triggeredBy.includes(';')) { //for cases that have additional conditions, remove them for the initial check
                triggeredBy = triggeredBy.split(';')[0];
            }
            let introOutro = buff.name.includes("Outro") || buff.name.includes("Intro");
            if (triggeredBy.length == 0 && introOutro) {
                triggeredBy = buff.name;
            }
            if (triggeredBy === 'Any')
                triggeredBy = skillRef.name; //well that's certainly one way to do it
            let triggeredByConditions = triggeredBy.split(',');
            //console.log("checking conditions for " + buff.name +"; applies to: " + buff.appliesTo + "; conditions: " + triggeredByConditions + "; special: " + buff.specialCondition);
            let isActivated = false;
            let specialActivated = false;
            let specialConditionValue = 0; //if there is a special >= condition, save this condition for potential proc counts later
            if (buff.specialCondition && !buff.specialCondition.includes('OnCast') && (buff.canActivate === 'Team' || buff.canActivate === activeCharacter)) { //special conditional
                if (buff.specialCondition.includes('>=')) {
                    // Extract the key and the value from the condition
                    let [key, value] = buff.specialCondition.split('>=', 2);
                    //console.log(`checking condition ${buff.specialCondition} for skill ${skillRef.name}; ${charData[activeCharacter].dCond.get(key)} >= ${value}`);

                    // Convert the value from string to number to compare
                    value = Number(value);

                    // Check if the property (key) exists in skillRef
                    if (charData[activeCharacter].dCond.has(key)) {
                        // Evaluate the condition
                        isActivated = charData[activeCharacter].dCond.get(key) >= value;
                        specialConditionValue = charData[activeCharacter].dCond.get(key);
                    } else {
                        console.log(`condition not found: ${buff.specialCondition} for skill ${skillRef.name}`);
                    }
                } else if (buff.specialCondition.includes(':')) {
                    let [key, value] = buff.specialCondition.split(':', 2);
                    if (key.includes('Buff')) { //check the presence of a buff
                        isActivated = false;
                        activeSet.forEach(activeBuff => { //loop through and look for if the buff already exists
                            if (activeBuff.buff.name == value) {
                                isActivated = true;
                            }
                        });
                    } else {
                        console.log(`unhandled colon condition: ${buff.specialCondition} for skill ${skillRef.name}`);
                    }
                } else {
                    console.log(`unhandled condition: ${buff.specialCondition} for skill ${skillRef.name}`);
                }
                specialActivated = isActivated;
            } else {
                specialActivated = true;
            }

            // check if any of the conditions in triggeredByConditions match
            isActivated = specialActivated && triggeredByConditions.some(function (condition) {
                condition = condition.trim();
                let conditionIsSkillName = condition.length > 2;
                let extraCondition = true;
                if (buff.additionalCondition) {
                    let extraConditions = buff.additionalCondition.split(",");
                    let foundExtra = false;
                    extraCondition = false;
                    extraConditions.forEach(additionalCondition => {
                        let found = additionalCondition.length == 2 ? skillRef.classifications.includes(additionalCondition) : skillRef.name.includes(additionalCondition);
                        if (found)
                            foundExtra = true;
                        //console.log(`checking for additional condition: ${additionalCondition}; length: ${additionalCondition.length}; skillRef class: ${skillRef.classifications}; skillRef name: ${skillRef.name}; fulfilled? ${found}`);
                    });
                    if (foundExtra)
                        extraCondition = true;
                }
                if (extraCondition) {
                    //console.log(`checking condition ${condition} for skill ${skillRef.name}; buff.canactivate: ${buff.canActivate}`);
                    if (condition.includes("Buff:")) { //check for the existence of a buff
                        let buffName = condition.split(":")[1];
                        console.log(`checking for the existence of ${buffName} at time ${currentTime}`);
                        let buffArray = Array.from(activeBuffs[activeCharacter]);
                        let buffArrayTeam = Array.from(activeBuffs['Team']);
                        let buffNames = buffArray.map(activeBuff => activeBuff.buff.name + (activeBuff.buff.type == "StackingBuff" ? (" x" + activeBuff.stacks) : "")); // Extract the name from each object
                        let buffNamesTeam = buffArrayTeam.map(activeBuff => activeBuff.buff.name + (activeBuff.buff.type == "StackingBuff" ? (" x" + activeBuff.stacks) : "")); // Extract the name from each object
                        let buffNamesString = buffNames.join(', ');
                        let buffNamesStringTeam = buffNamesTeam.join(', ');
                        return (buffNamesString.includes(buffName) || buffNamesStringTeam.includes(buffName));
                    } else if (conditionIsSkillName) {
                        passiveDamageQueue.forEach(passiveDamageQueued => {
                            console.log(`buff: ${buff.name}; passive damage queued: ${passiveDamageQueued != null}, condition: ${condition}, name: ${passiveDamageQueued != null ? passiveDamageQueued.name : "none"}, buff.canActivate: ${buff.canActivate}, owner: ${passiveDamageQueued != null ? passiveDamageQueued.owner : "none"}; additional condition: ${buff.additionalCondition}`);
                            if (passiveDamageQueued != null && ((passiveDamageQueued.name.includes(condition) || condition.includes(passiveDamageQueued.name)) || (condition === 'Passive' && passiveDamageQueued.limit != 1 && (passiveDamageQueued.type != 'TickOverTime' && buff.canActivate != 'Active')
                            )) && (buff.canActivate === passiveDamageQueued.owner || buff.canActivate === 'Team' || buff.canActivate === 'Active')) {
                                console.log("[skill name] passive damage queued exists - adding new buff " + buff.name);
                                passiveDamageQueued.addBuff(buff.type === 'StackingBuff' ? createActiveStackingBuff(buff, currentTime, 1) : createActiveBuff(buff, currentTime));
                            }
                        });
                        // the condition is a skill name, check if it's included in the currentSkill
                        let applicationCheck = buff.appliesTo === activeCharacter || buff.appliesTo === 'Team' || buff.appliesTo === 'Active' || introOutro || skillRef.source === activeCharacter;
                        //console.log(`condition is skill name. application check: ${applicationCheck}, buff.canActivate: ${buff.canActivate}, skillRef.source: ${skillRef.source}`);
                        if (condition === 'Swap' && !skillRef.name.includes('Intro') && (skillRef.castTime == 0 || skillRef.name.includes('(Swap)'))) { //this is a swap-out skill
                            return applicationCheck && ((buff.canActivate === activeCharacter || buff.canActivate === 'Team') || (skillRef.source === activeCharacter && introOutro));
                        } else {
                            return currentSkill.includes(condition) && applicationCheck && (buff.canActivate === activeCharacter || buff.canActivate === 'Team' || (skillRef.source === activeCharacter && buff.appliesTo === 'Next'));
                        }
                    } else {
                        //console.log(`passive damage queued: ${passiveDamageQueued != null}, condition: ${condition}, name: ${passiveDamageQueued != null ? passiveDamageQueued.name : "none"}, buff.canActivate: ${buff.canActivate}, owner: ${passiveDamageQueued != null ? passiveDamageQueued.owner : "none"}`);
                        passiveDamageQueue.forEach(passiveDamageQueued => {
                            if (passiveDamageQueued != null && passiveDamageQueued.classifications.includes(condition) && (buff.canActivate === passiveDamageQueued.owner || buff.canActivate === 'Team')) {
                                console.log("passive damage queued exists - adding new buff " + buff.name);
                                passiveDamageQueued.addBuff(buff.type === 'StackingBuff' ? createActiveStackingBuff(buff, currentTime, 1) : createActiveBuff(buff, currentTime));
                            }
                        });
                        // the condition is a classification code, check against the classification
                        //console.log(`checking condition: ${condition} healfound: ${healFound}`);
                        return (classification.includes(condition) || (condition === 'Hl' && healFound)) && (buff.canActivate === activeCharacter || buff.canActivate === 'Team');
                    }
                }
            });
            if (buff.name.startsWith("Incandescence") && skillRef.classifications.includes("Ec"))
                isActivated = false;
            if (isActivated) { //activate this effect
                let found = false;
                let applyToCurrent = true;
                let stacksToAdd = 1;
                console.log(`${buff.name} has been activated by ${skillRef.name} at ${currentTime}; type: ${buff.type}; appliesTo: ${buff.appliesTo}; class: ${buff.classifications}`);
                if (buff.classifications.includes(`Hl`)) { //when a heal effect is procced, raise a flag for subsequent proc conditions
                    healFound = true;
                }
                if (buff.type === 'ConsumeBuffInstant') { //these buffs are immediately withdrawn before they are calculating
                    removeBuffInstant.push(buff.classifications);
                } else if (buff.type === 'ConsumeBuff') {
                    if (removeBuff != null)
                        console.log("UNEXPECTED double removebuff condition.");
                    removeBuff = buff.classifications; //remove this later, after other effects apply
                } else if (buff.type === 'ResetBuff') {
                    let buffArray = Array.from(activeBuffs[activeCharacter]);
                    let buffArrayTeam = Array.from(activeBuffs['Team']);
                    let buffNames = buffArray.map(activeBuff => activeBuff.buff.name + (activeBuff.buff.type == "StackingBuff" ? (" x" + activeBuff.stacks) : "")); // Extract the name from each object
                    let buffNamesTeam = buffArrayTeam.map(activeBuff => activeBuff.buff.name + (activeBuff.buff.type == "StackingBuff" ? (" x" + activeBuff.stacks) : "")); // Extract the name from each object
                    let buffNamesString = buffNames.join(', ');
                    let buffNamesStringTeam = buffNamesTeam.join(', ');
                    if (!buffNamesString.includes(buff.name) && !buffNamesStringTeam.includes(buff.name)) {
                        console.log('adding new active resetbuff');
                        activeSet.add(createActiveBuff(buff, currentTime));
                    }
                } else if (buff.type === 'Dmg') { //add a new passive damage instance
                    //queue the passive damage and snapshot the buffs later
                    console.log("adding a new type of passive damage " + buff.name);
                    passiveDamageQueued = new PassiveDamage(buff.name, buff.classifications, buff.buffType, buff.amount, buff.duration, currentTime, buff.stackLimit, buff.stackInterval, buff.triggeredBy, activeCharacter, i, buff.dCond);
                    if (buff.buffType === 'TickOverTime' && !buff.name.includes('Inklet')) {
                        // for DOT effects, procs are only applied at the end of the interval
                        passiveDamageQueued.lastProc = currentTime;
                    }
                    passiveDamageQueue.push(passiveDamageQueued)
                    console.log(passiveDamageQueued);
                } else if (buff.type === 'StackingBuff') {
                    let effectiveInterval = buff.stackInterval;
                    if (buff.name.startsWith('Incandescence') && jinhsiOutroActive) {
                        effectiveInterval = 1;
                    }
                    console.log(`effectiveInterval: ${effectiveInterval}; casttime: ${skillRef.castTime}; hits: ${skillRef.numberOfHits}; freezetime: ${skillRef.freezeTime}`);
                    if (effectiveInterval < (skillRef.castTime - skillRef.freezeTime)) { //potentially add multiple stacks
                        let maxStacksByTime = effectiveInterval == 0 ? skillRef.numberOfHits : Math.floor((skillRef.castTime - skillRef.freezeTime) / effectiveInterval);
                        stacksToAdd = Math.min(maxStacksByTime, skillRef.numberOfHits);
                    }
                    if (buff.specialCondition && buff.specialCondition.includes('OnCast'))
                        stacksToAdd = 1;
                    if (buff.name === 'Resolution' && skillRef.name.startsWith("Intro: Tactical Strike"))
                        stacksToAdd = 15;
                    if (specialConditionValue > 0) //cap the stacks to add based on the special condition value
                        stacksToAdd = Math.min(stacksToAdd, specialConditionValue);
                    //console.log("this buff applies to: " + buff.appliesTo + "; active char: " + activeCharacter);
                    console.log(buff.name + " is a stacking buff (special condition: " + buff.specialCondition + "). attempting to add " + stacksToAdd + " stacks");
                    activeSet.forEach(activeBuff => { //loop through and look for if the buff already exists
                        if (activeBuff.buff.name == buff.name && activeBuff.buff.triggeredBy === buff.triggeredBy) {
                            found = true;
                            console.log(`current stacks: ${activeBuff.stacks} last stack: ${activeBuff.stackTime}; current time: ${currentTime}`);
                            if (currentTime - activeBuff.stackTime >= effectiveInterval) {
                                activeBuff.stacks = Math.min(activeBuff.stacks + stacksToAdd, buff.stackLimit);
                                activeBuff.stackTime = currentTime;
                                console.log("updating stacking buff: " + buff.name);
                            }
                        }
                    });
                    if (!found) { //add a new stackable buff
                        activeSet.add(createActiveStackingBuff(buff, currentTime, Math.min(stacksToAdd, buff.stackLimit)));
                        //console.log("adding new stacking buff: " + buff.name);
                    }
                } else {
                    if (buff.name.includes("Outro") || buff.appliesTo === 'Next') { //outro buffs are special and are saved for the next character
                        queuedBuffsForNext.push(createActiveBuff(buff, currentTime));
                        console.log("queuing buff for next: " + buff.name);
                        applyToCurrent = false;
                    } else {
                        activeSet.forEach(activeBuff => { //loop through and look for if the buff already exists
                            if (activeBuff.buff.name == buff.name) {
                                //if (currentTime >= activeBuff.availableIn) //if the buff is available to refresh, then refresh. BROKEN. FIX THIS LATER. (only applies to jinhsi unison right now which really doesnt change anything if procs more)
                                activeBuff.startTime = currentTime + skillRef.castTime;
                                //else
                                //  console.log(`the buff ${buff.name} is not available to refresh until ${activeBuff.availableIn}; its interval is ${activeBuff.stackInterval}`);
                                found = true;
                                console.log(`updating starttime of ${buff.name} to ${currentTime + skillRef.castTime}`);
                            }
                        });
                        if (!found) {
                            if (buff.type != 'BuffEnergy') //buffenergy availablein is updated when it is applied later on
                                buff.availableIn = currentTime + buff.stackInterval;
                            activeSet.add(createActiveBuff(buff, currentTime + skillRef.castTime));
                            //console.log("adding new buff: " + buff.name);
                        }
                    }
                }
                if (buff.dCond != null) {
                    buff.dCond.forEach((value, condition) => {
                        evaluateDCond(value * stacksToAdd, condition);
                    });
                }
            }
        });

        removeBuffInstant.forEach(removeBuff => {
            if (removeBuff != null) {
                for (let activeBuff of activeBuffs[activeCharacter]) {
                    if (activeBuff.buff.name.includes(removeBuff)) {
                        activeBuffs[activeCharacter].delete(activeBuff);
                        console.log(`removing buff instantly: ${activeBuff.buff.name}`);
                    }
                }
                for (let activeBuff of activeBuffs['Team']) {
                    if (activeBuff.buff.name.includes(removeBuff)) {
                        activeBuffs['Team'].delete(activeBuff);
                        console.log(`removing buff instantly: ${activeBuff.buff.name}`);
                    }
                }
            }
        });

        activeBuffsArray = Array.from(activeBuffs[activeCharacter]);
        let buffNames = activeBuffsArray.map(activeBuff => activeBuff.buff.name + (activeBuff.buff.type == "StackingBuff" ? (" x" + activeBuff.stacks) : "")); // Extract the name from each object
        let buffNamesString = buffNames.join(', ');

        //console.log(buffNamesString);
        /*activeBuffs[activeCharacter].forEach(buff => {
          console.log(buff);
        });*/

        //console.log("Writing to: " + (dataCellCol + i) + "; " + buffNamesString);
        if (activeBuffsArray.length == 0) {
            if (ITERATIVE)
                rotationSheet.getRange(dataCellCol + i).setValue("(0)");
            else
                writeBuffsPersonal.push(["(0)"]);
        } else {
            let buffString = "(" + activeBuffsArray.length + ") " + buffNamesString;
            if (ITERATIVE)
                rotationSheet.getRange(dataCellCol + i).setValue(buffString);
            else
                writeBuffsPersonal.push([buffString]);
        }

        activeBuffsArrayTeam = Array.from(activeBuffs['Team']);
        let buffNamesTeam = activeBuffsArrayTeam.map(activeBuff => activeBuff.buff.name + (activeBuff.buff.type == "StackingBuff" ? (" x" + activeBuff.stacks) : "")); // extract the name from each object
        let buffNamesStringTeam = buffNamesTeam.join(', ');

        console.log("buff names string team: " + buffNamesStringTeam);
        /*activeBuffs['Team'].forEach(buff => {
          console.log(buff);
        });*/

        //console.log("Writing to: " + (dataCellColTeam + i) + "; " + `(${activeBuffsArrayTeam.length}) ${buffNamesStringTeam}`);
        //rotationSheet.getRange('A10').setValue(`(${activeBuffsArrayTeam.length}) ${buffNamesStringTeam}`);
        if (buffNamesStringTeam.length == 0) {
            if (ITERATIVE)
                rotationSheet.getRange(dataCellColTeam + i).setValue("(0)");
            else
                writeBuffsTeam.push(["(0)"]);
        } else {
            let buffString = `(${activeBuffsArrayTeam.length}) ${buffNamesStringTeam}`;
            if (ITERATIVE)
                rotationSheet.getRange(dataCellColTeam + i).setValue(buffString);
            else
                writeBuffsTeam.push([buffString]);

        }

        /**
         * Updates the total buff map.
         * @buffCategory - The base type of the buff (All , AllEle, Fu, Sp, etc)
         * @buffType - The specific type of the buff (Bonus, Attack, Additive)
         * @buffAmount - The amount of the buff to add
         * @buffMax - The maximum buff value for the stack, for particular buffs have multiple different variations contributing to the same cap (e.g. Jinhsi Incandesence)
         */
        function updateTotalBuffMap(buffCategory, buffType, buffAmount, buffMax) {
            //console.log(`updating buff for ${buffCategory}; type=${buffType}; amount=${buffAmount}; max=${buffMax}`);
            let key = buffCategory;
            if (buffCategory === 'All') {
                STANDARD_BUFF_TYPES.forEach(buff => {
                    let newKey = translateClassificationCode(buff);
                    newKey = buffType === 'Deepen' ? `${newKey} (${buffType})` : `${newKey}`;
                    let currentAmount = totalBuffMap.get(newKey);
                    if (!totalBuffMap.has(newKey)) {
                        return;
                    }
                    totalBuffMap.set(newKey, currentAmount + buffAmount); // Update the total amount
                    //console.log("updating buff " + newKey + " to " + (currentAmount) + " (+" + buffAmount + ")");
                });
            } else if (buffCategory === 'AllEle') {
                ELEMENTAL_BUFF_TYPES.forEach(buff => {
                    let newKey = translateClassificationCode(buff);
                    let currentAmount = totalBuffMap.get(newKey);
                    if (!totalBuffMap.has(newKey)) {
                        return;
                    }
                    totalBuffMap.set(newKey, currentAmount + buffAmount); // Update the total amount
                    //console.log("updating buff " + newKey + " to " + (currentAmount) + " (+" + buffAmount + ")");
                });
            } else {
                var categories = buffCategory.split(',');
                categories.forEach(category => {
                    let newKey = translateClassificationCode(category);
                    var baseKey = newKey.replace(/\s*\(.*?\)\s*/g, '');
                    newKey = buffType === 'Deepen' ? `${newKey} (${buffType})` : `${newKey}`;
                    let currentAmount = totalBuffMap.get(newKey);
                    if (buffType.includes('*')) { //this is a dynamic buff value that multiplies by a certain condition
                        let split = buffType.split("*");
                        buffType = split[0];
                        buffAmount = buffAmount * charData[activeCharacter].dCond.get(split[1]);
                        console.log(`found multiplicative condition for buff amount: multiplying ${buffAmount} by ${split[1]} (${charData[activeCharacter].dCond.get(split[1])})`);
                    }
                    let buffKey = buffType === 'Bonus' ? 'Specific' : (buffType === 'Deepen' ? 'Deepen' : 'Multiplier');
                    if (buffType === 'Additive') { //an additive value to a skill multiplier
                        //todo
                        buffKey = 'Additive';
                        newKey = `${baseKey} (${buffKey})`;
                        if (totalBuffMap.has(newKey)) {
                            let currentBonus = totalBuffMap.get(newKey);
                            let maxValue = 99999;
                            if (buffMax > 0) {
                                maxValue = buffMax;
                            }
                            totalBuffMap.set(newKey, Math.min(maxValue, currentBonus + buffAmount)); // Update the total amount
                            console.log(`updating ${newKey}: ${currentBonus} + ${buffAmount}, capped at ${maxValue}`);
                        } else { //add the skill key as a new value for potential procs
                            totalBuffMap.set(newKey, buffAmount);
                            console.log(`no match, but adding additive key ${newKey} = ${buffAmount}`)
                        }
                    } else if (buffKey === 'Deepen' && !STANDARD_BUFF_TYPES.includes(baseKey)) { //apply element-specific deepen effects IF MATCH
                        if ((category.length == 2 && skillRef.classifications.includes(category)) || (category.length > 2 &&
                            skillRef.name.includes(category))) {
                            newKey = 'Deepen';
                            currentAmount = totalBuffMap.get(newKey);
                            console.log("updating amplify; current " + (currentAmount) + " (+" + buffAmount + ")");
                            totalBuffMap.set(newKey, currentAmount + buffAmount); // Update the total amount
                        }
                    } else if (buffType === 'Resistance') { //apply resistance effects IF MATCH
                        if ((category.length == 2 && skillRef.classifications.includes(category)) || (category.length > 2 &&
                            skillRef.name.includes(category))) {
                            newKey = 'Resistance';
                            currentAmount = totalBuffMap.get(newKey);
                            console.log("updating res shred; current " + (currentAmount) + " (+" + buffAmount + ")");
                            totalBuffMap.set(newKey, currentAmount + buffAmount); // Update the total amount
                        }
                    } else if (buffType === 'Ignore Defense') { //ignore defense IF MATCH
                        if ((category.length == 2 && skillRef.classifications.includes(category)) || (category.length > 2 &&
                            skillRef.name.includes(category))) {
                            newKey = 'Ignore Defense';
                            currentAmount = totalBuffMap.get(newKey);
                            console.log("updating ignore def; current " + (currentAmount) + " (+" + buffAmount + ")");
                            totalBuffMap.set(newKey, currentAmount + buffAmount); // Update the total amount
                        }
                    } else {
                        if (!totalBuffMap.has(newKey)) { //skill-specific buff
                            if (skillRef.name.includes(newKey)) {
                                let currentBonus = totalBuffMap.get(buffKey);
                                totalBuffMap.set(buffKey, currentBonus + buffAmount); // Update the total amount
                                console.log(`updating new key from ${newKey}; current bonus: ${currentBonus}; buffKey: ${buffKey}; buffAmount: ${buffAmount}`);
                            } else { //add the skill key as a new value for potential procs
                                totalBuffMap.set(`${newKey} (${buffKey})`, buffAmount);
                                console.log(`no match, but adding key ${newKey} (${buffKey})`)
                            }
                        } else {
                            totalBuffMap.set(newKey, currentAmount + buffAmount); // Update the total amount
                        }
                    }
                    //console.log("updating buff " + key + " to " + (currentAmount) + " (+" + buffAmount + ")");
                });
            }
        }

        // Process buff array
        function processBuffs(buffs) {
            buffs.forEach(buffWrapper => {
                let buff = buffWrapper.buff;
                console.log(`buff: ${buff.name}; buffType: ${buff.type}; current time: ${currentTime}; available In: ${buff.availableIn}`);
                if (buff.name === 'Rythmic Vibrato') { //we don't re-poll buffs for passive damage instances currently so it needs to keep track of this lol
                    rythmicVibrato = buffWrapper.stacks;
                }

                if (buff.type === "BuffEnergy" && currentTime >= buff.availableIn) { //add energy instead of adding the buff
                    console.log("adding BuffEnergy dynamic condition: " + buff.amount + " for type " + buff.buffType);
                    buff.availableIn = currentTime + buff.stackInterval;
                    charData[activeCharacter].dCond.set(buff.buffType, Number(charData[activeCharacter].dCond.get(buff.buffType)) + Number(buff.amount) * Math.max(Number(buffWrapper.stacks), 1));
                    console.log(`total ${buff.buffType} after: ${charData[activeCharacter].dCond.get(buff.buffType)}`);
                }

                // special buff types are handled slightly differently
                let specialBuffTypes = ['Attack', 'Health', 'Defense', 'Crit', 'Crit Dmg'];
                if (specialBuffTypes.includes(buff.buffType)) {
                    if (buff.classifications === 'All' || ((buff.classifications.length == 2 && skillRef.classifications.includes(buff.classifications)) || skillRef.name.includes(buff.classifications)))
                        updateTotalBuffMap(buff.buffType, '', buff.amount * (buff.type === 'StackingBuff' ? buffWrapper.stacks : 1), buff.amount * buff.stackLimit);
                } else { // for other buffs, just use classifications as is
                    updateTotalBuffMap(buff.classifications, buff.buffType, buff.amount * (buff.type === 'StackingBuff' ? buffWrapper.stacks : 1), buff.amount * buff.stackLimit);
                }
            });
        }

        function writeBuffsToSheet(i) {
            var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Calculator');
            var keysIterator = totalBuffMap.keys();

            var bufferRange = sheet.getRange("I" + i + ":AG" + i);
            var values = [];

            for (let key of keysIterator) {
                let value = totalBuffMap.get(key);
                if (key === 'Attack')
                    value += bonusStats[activeCharacter].attack;
                if (key === 'Health')
                    value += bonusStats[activeCharacter].health;
                if (key === 'Defense')
                    value += bonusStats[activeCharacter].defense;
                if (key === 'Crit')
                    value += charData[activeCharacter].crit;
                if (key === 'Crit Dmg')
                    value += charData[activeCharacter].critDmg;
                values.push(value);
                //console.log(key + " value : " + totalBuffMap.get(key))
            }

            if (values.length > 25) {
                values = values.slice(0, 25);
            }
            if (ITERATIVE)
                bufferRange.setValues([values])
            else
                writeStats.push(values);
        }

        let totalBuffMap = new Map([
            ['Attack', 0],
            ['Health', 0],
            ['Defense', 0],
            ['Crit', 0],
            ['Crit Dmg', 0],
            ['Normal', 0],
            ['Heavy', 0],
            ['Skill', 0],
            ['Liberation', 0],
            ['Normal (Deepen)', 0],
            ['Heavy (Deepen)', 0],
            ['Skill (Deepen)', 0],
            ['Liberation (Deepen)', 0],
            ['Physical', 0],
            ['Glacio', 0],
            ['Fusion', 0],
            ['Electro', 0],
            ['Aero', 0],
            ['Spectro', 0],
            ['Havoc', 0],
            ['Specific', 0],
            ['Deepen', 0],
            ['Multiplier', 0],
            ['Resistance', 0],
            ['Ignore Defense', 0],
            ['Flat Attack', 0],
            ['Flat Health', 0],
            ['Flat Defense', 0],
            ['Energy Regen', 0]
        ]);
        let teamBuffMap = Object.assign({}, totalBuffMap);

        if (totalBuffMap.has(weaponData[activeCharacter].mainStat)) {
            let currentAmount = totalBuffMap.get(weaponData[activeCharacter].mainStat);
            totalBuffMap.set(weaponData[activeCharacter].mainStat, currentAmount + weaponData[activeCharacter].mainStatAmount);
            console.log("adding mainstat " + weaponData[activeCharacter].mainStat + " (+" + weaponData[activeCharacter].mainStatAmount + ") to " + activeCharacter);
        }
        console.log("BONUS STATS:");
        console.log(charData[activeCharacter].bonusStats);
        charData[activeCharacter].bonusStats.forEach((statPair) => {
            let stat = statPair[0];
            let value = statPair[1];
            let currentAmount = totalBuffMap.get(stat) || 0;
            totalBuffMap.set(stat, currentAmount + value);
        });
        processBuffs(activeBuffsArray);

        processBuffs(activeBuffsArrayTeam);
        lastTotalBuffMap[activeCharacter] = totalBuffMap;


        passiveDamageQueue.forEach(passiveDamageQueued => {
            if (passiveDamageQueued != null) { //snapshot passive damage BEFORE team buffs are applied
                //TEMP: move this above activeBuffsArrayTeam and implement separate buff tracking
                for (let j = 0; j < passiveDamageInstances.length; j++) { //remove any duplicates first
                    if (passiveDamageInstances[j].name === passiveDamageQueued.name) {
                        passiveDamageInstances[j].remove = true;
                        console.log(`new instance of passive damage ${passiveDamageQueued.name} found. removing old entry`);
                        break;
                    }
                }
                passiveDamageQueued.setTotalBuffMap(totalBuffMap);
                passiveDamageInstances.push(passiveDamageQueued);
            }
        });

        writeBuffsToSheet(i);
        if (skillRef.type.includes("Buff")) {
            rotationSheet.getRange(dataCellColDmg + i).setValue(0);
            continue;
        }

        //damage calculations
        //console.log(charData[activeCharacter]);
        //console.log("bonus input stats:");
        //console.log(bonusStats[activeCharacter]);
        console.log("DAMAGE CALC for : " + skillRef.name);
        console.log(skillRef);
        console.log("multiplier: " + totalBuffMap.get('Multiplier'));
        passiveDamageInstances = passiveDamageInstances.filter(passiveDamage => !passiveDamage.canRemove(currentTime, removeBuff));

        function evaluateDCond(value, condition) {
            if (value && value != 0) {
                //console.log(`evaluating dynamic condition for ${skillRef.name}: ${condition} x${value}`);
                if (value < 0) {
                    var cellInfo = rotationSheet.getRange('B' + i);
                    if (activeCharacter === 'Jinhsi' && condition === 'Concerto' && buffNames.includes("Unison")) {
                        cellInfo.setNote(`The Unison condition has covered the Conerto cost for this Outro.`);
                    } else {
                        if (charData[activeCharacter].dCond.get(condition) + value < 0) { //ILLEGAL INPUT
                            cellInfo.setFontColor('#ff0000');
                            if (condition === 'Resonance') {
                                var energyRecharge = (weaponData[activeCharacter].mainStat === 'Energy Regen' ? weaponData[activeCharacter].mainStatAmount : 0) + bonusStats[activeCharacter].energyRecharge + (charData[activeCharacter].bonusStats.find(element => element[0] === 'Energy Regen')?.[1] || 0);
                                var baseEnergy = charData[activeCharacter].dCond.get(condition) / (1 + energyRecharge);
                                var requiredRecharge = ((value * -1) / baseEnergy - energyRecharge - 1) * 100;
                                cellInfo.setNote(`Illegal rotation! At this point, you have ${charData[activeCharacter].dCond.get(condition).toFixed(2)} out of the required ${(value * -1)} ${condition} (Requires an additional ${requiredRecharge.toFixed(1)}% ERR)`);
                            } else {
                                var noMessage = false;
                                if (activeCharacter === 'Jiyan' && skillRef.name.includes("Windqueller"))
                                    noMessage = true;
                                if (!noMessage)
                                    cellInfo.setNote(`Illegal rotation! At this point, you have ${charData[activeCharacter].dCond.get(condition).toFixed(2)} out of the required ${(value * -1)} ${condition}`);
                            }
                            initialDCond[activeCharacter].set(condition, (value * -1) - charData[activeCharacter].dCond.get(condition));
                        } else
                            cellInfo.setNote(`At this point, you have generated ${charData[activeCharacter].dCond.get(condition).toFixed(2)} out of the required ${(value * -1)} ${condition}`);
                        if (activeCharacter === 'Danjin' || skillRef.name.startsWith("Outro") || skillRef.name.startsWith("Liberation"))
                            charData[activeCharacter].dCond.set(condition, 0); //consume all
                        else {
                            if (activeCharacter === 'Jiyan' && buffNames.includes("Qingloong Mode") && skillRef.name.includes("Windqueller")) { //increase skill damage bonus for this action if forte was consumed, but only if ult is NOT active
                                let currentAmount = totalBuffMap.get('Specific');
                                totalBuffMap.set('Specific', currentAmount + 0.2);
                            } else { //adjust the dynamic condition as expected
                                charData[activeCharacter].dCond.set(condition, Math.max(0, charData[activeCharacter].dCond.get(condition) + value));
                            }
                        }
                    }
                } else {
                    if (!charData[activeCharacter].dCond.get(condition)) {
                        console.log("EH? NaN condition " + condition + " for character " + activeCharacter);
                        charData[activeCharacter].dCond.set(condition, 0);
                    };
                    if (condition === 'Resonance') {
                        handleEnergyShare(value, activeCharacter);
                    } else {
                        if (condition === 'Forte') {
                            console.log(`maximum forte: ${CHAR_CONSTANTS[activeCharacter].maxForte}; current: ${Math.min(charData[activeCharacter].dCond.get(condition))}; value to add: ${value}`);
                            charData[activeCharacter].dCond.set(condition, Math.min(charData[activeCharacter].dCond.get(condition) + value, CHAR_CONSTANTS[activeCharacter].maxForte));
                        } else
                            charData[activeCharacter].dCond.set(condition, charData[activeCharacter].dCond.get(condition) + value);
                    }
                }
                console.log(charData[activeCharacter]);
                console.log(charData[activeCharacter].dCond);
                console.log(`dynamic condition [${condition}] updated: ${charData[activeCharacter].dCond.get(condition)} (+${value})`);
            }
        }

        skillRef.dCond.forEach((value, condition) => {
            evaluateDCond(value, condition);
        });
        let passiveCurrentSlot = false; //if a passive damage procs on the same slot, we need to add the damage to the current value later
        if (skillRef.damage > 0) {
            passiveDamageInstances.forEach(passiveDamage => {
                console.log("checking proc conditions for " + passiveDamage.name + "; " + passiveDamage.canProc(currentTime, skillRef) + " (" + skillRef.name + ")");
                if (passiveDamage.canProc(currentTime, skillRef) && passiveDamage.checkProcConditions(skillRef)) {
                    passiveDamage.updateTotalBuffMap();
                    let procs = passiveDamage.handleProcs(currentTime, skillRef.castTime - skillRef.freezeTime, skillRef.numberOfHits);
                    var damageProc = passiveDamage.calculateProc(activeCharacter) * procs;
                    if (ITERATIVE) {
                        let cell = rotationSheet.getRange(dataCellColDmg + passiveDamage.slot);
                        let currentDamage = cell.getValue();
                        cell.setValue(currentDamage + damageProc);
                        var cellInfo = rotationSheet.getRange('H' + passiveDamage.slot);
                        cellInfo.setFontWeight('bold');
                        cellInfo.setNote(passiveDamage.getNote());
                    } else {
                        if (passiveDamage.slot == i) {
                            writeDamage[passiveDamage.slot - ROTATION_START] = damageProc;
                            passiveCurrentSlot = true;
                        } else
                            writeDamage[passiveDamage.slot - ROTATION_START] += damageProc;
                        writeDamageNote[passiveDamage.slot - ROTATION_START] = passiveDamage.getNote();
                    }
                }
            });
        }
        if (ITERATIVE) {
            rotationSheet.getRange('D' + i).setValue(charData[activeCharacter].dCond.get('Resonance').toFixed(2));
            rotationSheet.getRange('E' + i).setValue(charData[activeCharacter].dCond.get('Concerto').toFixed(2));
        } else {
            writeResonance.push([charData[activeCharacter].dCond.get('Resonance').toFixed(2)]);
            writeConcerto.push([charData[activeCharacter].dCond.get('Concerto').toFixed(2)]);
        }

        var additiveValueKey = `${skillRef.name} (Additive)`;
        var damage = skillRef.damage * (skillRef.classifications.includes("Ec") ? 1 : skillLevelMultiplier) + (totalBuffMap.has(additiveValueKey) ? totalBuffMap.get(additiveValueKey) : 0);
        var attack = (charData[activeCharacter].attack + weaponData[activeCharacter].attack) * (1 + totalBuffMap.get('Attack') + bonusStats[activeCharacter].attack) + totalBuffMap.get('Flat Attack');
        var health = charData[activeCharacter].health * (1 + totalBuffMap.get('Health') + bonusStats[activeCharacter].health) + totalBuffMap.get('Flat Health');
        var defense = charData[activeCharacter].defense * (1 + totalBuffMap.get('Defense') + bonusStats[activeCharacter].defense) + totalBuffMap.get('Flat Defense');
        var critMultiplier = (1 - Math.min(1, (charData[activeCharacter].crit + totalBuffMap.get('Crit')))) * 1 + Math.min(1, (charData[activeCharacter].crit + totalBuffMap.get('Crit'))) * (charData[activeCharacter].critDmg + totalBuffMap.get('Crit Dmg'));
        var damageMultiplier = getDamageMultiplier(skillRef.classifications, totalBuffMap);
        //console.log(`char defense: ${charData[activeCharacter].defense} weapon def: ${weaponData[activeCharacter].defense}; buff def: ${totalBuffMap.get('Defense')} bonus stat def: ${bonusStats[activeCharacter].defense}; flat def: ${totalBuffMap.get('Flat Defense')}`)
        var scaleFactor = skillRef.classifications.includes('Df') ? defense : (skillRef.classifications.includes('Hp') ? health : attack);
        var totalDamage = damage * scaleFactor * critMultiplier * damageMultiplier * (weaponData[activeCharacter].weapon.name === 'Nullify Damage' ? 0 : 1);
        //console.log(charData[activeCharacter]);
        //console.log(weaponData[activeCharacter]);
        console.log(`skill damage: ${damage.toFixed(2)}; attack: ${(charData[activeCharacter].attack + weaponData[activeCharacter].attack).toFixed(2)} x ${(1 + totalBuffMap.get('Attack') + bonusStats[activeCharacter].attack).toFixed(2)} + ${totalBuffMap.get('Flat Attack')}; crit mult: ${critMultiplier.toFixed(2)}; dmg mult: ${damageMultiplier.toFixed(2)}; defense: ${defense}; total dmg: ${totalDamage.toFixed(2)}`);
        if (ITERATIVE) {
            rotationSheet.getRange(dataCellColDmg + i).setValue(rotationSheet.getRange(dataCellColDmg + i).getValue() + totalDamage);
        } else {
            if (passiveCurrentSlot)
                writeDamage[writeDamage.length - 1] += totalDamage;
            else
                writeDamage.push(totalDamage);
            writeDamageNote.push('');
        }

        updateDamage(skillRef.name, skillRef.classifications, activeCharacter, damage, totalDamage, totalBuffMap);
        if (mode === 'Opener' && character1 === activeCharacter && skillRef.name.startsWith('Outro')) {
            mode = 'Loop';
            openerTime = rotationSheet.getRange(`C${i}`).getValue();
        }
        liveTime += skillRef.castTime; //live time

        if (removeBuff != null) {
            for (let activeBuff of activeBuffs[activeCharacter]) {
                if (activeBuff.buff.name.includes(removeBuff)) {
                    activeBuffs[activeCharacter].delete(activeBuff);
                    console.log(`removing buff: ${activeBuff.buff.name}`);
                }
            }
            for (let activeBuff of activeBuffs['Team']) {
                if (activeBuff.buff.name.includes(removeBuff)) {
                    activeBuffs['Team'].delete(activeBuff);
                    console.log(`removing buff: ${activeBuff.buff.name}`);
                }
            }
        }
    }

    var startRow = dataCellRowNextSub;
    var startColIndex = SpreadsheetApp.getActiveSpreadsheet().getRange(dataCellColNextSub + "1").getColumn(); // Get the column index for 'I' which is 9

    //console.log(charStatGains[characters[0]]);
    //console.log(charEntries[characters[0]]);

    function convertToColumnArray(arr) {
        return arr.map(item => [item]);
    }

    if (!ITERATIVE) { //
        console.log("===EXECUTION COMPLETE===");
        console.log("updating cells...")


        let rangeReso = `${dataCellColReso}${ROTATION_START}:${dataCellColReso}${endLine}`;
        let rangeConcerto = `${dataCellColConcerto}${ROTATION_START}:${dataCellColConcerto}${endLine}`;
        let rangePersonalBuff = `${dataCellCol}${ROTATION_START}:${dataCellCol}${endLine}`;
        let rangeTeamBuff = `${dataCellColTeam}${ROTATION_START}:${dataCellColTeam}${endLine}`;
        let rangeResults = `${dataCellColResults}${ROTATION_START}:AG${endLine}`;
        let rangeDamage = `${dataCellColDmg}${ROTATION_START}:${dataCellColDmg}${endLine}`;

        rotationSheet.getRange(rangeReso).setValues(writeResonance);
        rotationSheet.getRange(rangeConcerto).setValues(writeConcerto);
        rotationSheet.getRange(rangePersonalBuff).setValues(writeBuffsPersonal);
        rotationSheet.getRange(rangeTeamBuff).setValues(writeBuffsTeam);
        rotationSheet.getRange(rangeResults).setValues(writeStats);
        rotationSheet.getRange(rangeDamage).setValues(convertToColumnArray(writeDamage));

        for (let i = 0; i < writeDamageNote.length; i++) {
            let trueIndex = ROTATION_START + i;
            if (writeDamageNote[i].length > 0) { //only write if there's actually something
                rotationSheet.getRange(`${dataCellColDmg}${trueIndex}`).setNote(writeDamageNote[i]);
                rotationSheet.getRange(`${dataCellColDmg}${trueIndex}`).setFontWeight('bold');
            }
        }
    }

    var finalTime = rotationSheet.getRange(`C${ROTATION_END}`).getValue();
    console.log(`real time: ${liveTime}; final in-game time: ${rotationSheet.getRange(`C${ROTATION_END}`).getValue()}`);
    rotationSheet.getRange('H27').setNote(`Total Damage: ${openerDamage.toFixed(2)} in ${openerTime.toFixed(2)}s`)
    rotationSheet.getRange('H28').setNote(`Total Damage: ${loopDamage.toFixed(2)} in ${(finalTime - openerTime).toFixed(2)}s`)
    rotationSheet.getRange('H27').setValue(openerTime > 0 ? openerDamage / openerTime : 0);
    rotationSheet.getRange('H28').setValue(loopDamage / (finalTime - openerTime));

    var wDpsLoopTime = 120 - openerTime;
    var wDpsLoops = wDpsLoopTime / (finalTime - openerTime)
    var wDps = (openerDamage + loopDamage * wDpsLoops) / 120;

    rotationSheet.getRange('H29').setValue(wDps.toFixed(2));
    if (CHECK_STATS) {
        for (var i = 0; i < characters.length; i++) {
            if (charEntries[characters[i]] > 0) { // Using [characters[i]] to get each character's entry
                var stats = charStatGains[characters[i]];
                var colOffset = 0; // Initialize column offset for each character

                Object.keys(stats).forEach(function (key) {
                    if (damageByCharacter[characters[i]] == 0)
                        stats[key] = 0;
                    else
                        stats[key] /= damageByCharacter[characters[i]]; //charEntries[characters[i]];
                    // Calculate the range using row and column indices and write data horizontally.
                    var cell = rotationSheet.getRange(startRow, startColIndex + colOffset);
                    cell.setValue(stats[key]);
                    colOffset++; // Move to the next column for the next stat
                });
                console.log(charStatGains[characters[i]]);
                startRow++; // Move to the next row after writing all stats for a character
            }
        }
    }

    var resultIndex = dataCellRowResults;
    console.log(totalDamageMap);
    for (let [key, value] of totalDamageMap) {
        rotationSheet.getRange(dataCellColResults + (resultIndex++)).setValue(value);
    }

    //write initial and final dconds

    startRow = dataCellRowDCond; // Starting at 66
    startColIndex = SpreadsheetApp.getActiveSpreadsheet().getRange(dataCellColDCond + "1").getColumn();
    characters.forEach(character => {
        var colOffset = 0; // Initialize column offset for each character
        rotationSheet.getRange(startRow, startColIndex + colOffset).setValue(initialDCond[character].get('Forte'));
        rotationSheet.getRange(startRow, startColIndex + (colOffset + 1)).setValue(initialDCond[character].get('Resonance'));
        rotationSheet.getRange(startRow, startColIndex + (colOffset + 2)).setValue(initialDCond[character].get('Concerto'));
        rotationSheet.getRange(startRow, startColIndex + colOffset + 3).setValue(charData[character].dCond.get('Forte'));
        rotationSheet.getRange(startRow, startColIndex + (colOffset + 4)).setValue(charData[character].dCond.get('Resonance'));
        rotationSheet.getRange(startRow, startColIndex + (colOffset + 5)).setValue(charData[character].dCond.get('Concerto'));
        startRow++;
    });

    exportBuild();

    // Output the tracked buffs for each time point (optional)
    trackedBuffs.forEach(entry => {
        Logger.log('Time: ' + entry.time + ', Active Buffs: ' + entry.activeBuffs.join(', '));
    });
}

function importBuild() {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Calculator');
    let errorRange = 'I25';
    let buildRange = 'K24';
    let confirmRange = 'N24';
    let build = rotationSheet.getRange(buildRange).getValue();
    let confirm = rotationSheet.getRange(confirmRange).getValue();
    rotationSheet.getRange(errorRange).setValue("");

    if (!confirm) {
        if (build && build.length > 0) {
            rotationSheet.getRange(errorRange).setValue("A build to import was found, but the confirmation checkbox was not set.");
            console.log("A build to import was found, but the confirmation checkbox was not set.")
        }
    } else if (build && build.length > 0) {

        var range = rotationSheet.getRange(`A${ROTATION_START}:B${ROTATION_END}`);

        range.setValue('');
        range.setFontWeight('normal');
        range.clearNote();
        let sections = build.split(';');
        if (sections.length != 5) {
            rotationSheet.getRange(errorRange).setValue(`Malformed build. Could not import. Found ${sections.length} sections; expected 5`);
        } else {
            let rotaSection = sections[4];
            let charSections = '';
            let divider = '';
            for (let i = 1; i < 4; i++) { //import the 3 character sections
                charSections += divider;
                charSections += sections[i];
                divider = ';';
            }
            /*for (let i = 0; i < 3; i++) {
              console.log(sections[i + 1]);
              rotationSheet.getRange(`B${7 + i}`).setValue(sections[i + 1].split(',')[0]);
            }
            Utilities.sleep(2000);*/

            //import the base character details
            const rowMappings = [
                { cellRange: 'B7:Z7', percentRange: 'L7:Z7', extraRange: 'I11:L11' },
                { cellRange: 'B8:Z8', percentRange: 'L8:Z8', extraRange: 'I12:L12' },
                { cellRange: 'B9:Z9', percentRange: 'L9:Z9', extraRange: 'I13:L13' }
            ];

            let rows = charSections.split(';'); // Split by each character input block

            for (let rowIndex = 0; rowIndex < rowMappings.length && rowIndex < rows.length; rowIndex++) {
                let values = rows[rowIndex].split(',');

                if (values.length < 29) {
                    Logger.log(`Row ${rowIndex + 1} does not contain the required 29 values.`);
                    continue; // Skip this row if it doesn't have enough values
                }

                let cellRange = rowMappings[rowIndex].cellRange;
                let percentRange = rowMappings[rowIndex].percentRange;
                let extraRange = rowMappings[rowIndex].extraRange;

                var weaponRange = 'D7:D9';
                var weaponRangeRules = sheet.getRange(weaponRange).getDataValidations();
                sheet.getRange(weaponRange).clearDataValidations();

                try {
                    // Get the first 25 values for cells Bx to Zx
                    let mainValues = values.slice(0, 25);
                    // Get the last 4 values for cells Ix to Lx
                    let extraValues = values.slice(25, 29);

                    // Convert 1D arrays to 2D arrays for setValues
                    let mainValues2D = [mainValues];
                    let extraValues2D = [extraValues];

                    // Set values in one batch operation for the main cells
                    sheet.getRange(cellRange).setValues(mainValues2D);

                    // Set values in one batch operation for the extra cells
                    sheet.getRange(extraRange).setValues(extraValues2D);

                    // Format specific columns as percentages (L to Z) for main values
                    sheet.getRange(percentRange).setNumberFormat('0.00%');

                    // Format extra columns (I to L) as percentages
                    sheet.getRange(extraRange).setNumberFormat('0.00%');
                } catch (e) {
                    console.log('error in importing build: ' + e);
                } finally {
                    sheet.getRange(weaponRange).setDataValidations(weaponRangeRules);
                }
            }

            //import the rotation

            const startingRow = 34;

            let entries = rotaSection.split(',');

            // Prepare arrays to hold character names and skills separately
            let characterData = [];
            let skillData = [];

            entries.forEach((entry, index) => {
                let [character, skill] = entry.split('&');
                characterData.push([character]);
                skillData.push([skill]);
            });

            // Get ranges for characters and skills
            let characterRange = sheet.getRange(`A${startingRow}:A${startingRow + characterData.length - 1}`);
            let skillRange = sheet.getRange(`B${startingRow}:B${startingRow + skillData.length - 1}`);

            //var skillValidationRules = skillRange.getDataValidations();
            //skillRange.clearDataValidations();

            try {
                // Batch update characters (column A)
                characterRange.setValues(characterData);

                // Wait briefly to allow drop-downs to refresh
                //Utilities.sleep(3000);

                // Batch update skills (column B)
                skillRange.setValues(skillData);
                rotationSheet.getRange(confirmRange).setValue(false);
            } catch (e) {
                console.log('error in importing build: ' + e);
            } finally {
                //rebuildRotationValidation();
            }
        }

    }
}

function rebuildRotationValidation() {
    var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = spreadsheet.getSheetByName("Calculator");

    // Define the range on the "Calculator" sheet
    var range = sheet.getRange("B34:B145");

    // Define the source range for the dropdown options on the "RotaSkills" sheet
    var sourceSheet = spreadsheet.getSheetByName("RotaSkills");
    var sourceRange = sourceSheet.getRange("$A1:$AA1");

    // Create the data validation rule for a dropdown based on the source range
    var rule = SpreadsheetApp.newDataValidation()
        .requireValueInRange(sourceRange, true)  // true indicates auto-advanced validation
        .setAllowInvalid(false)  // Optional: do not allow invalid entries
        .build();

    // Apply the validation rule to the target range
    range.setDataValidation(rule);
}

function updateDamage(name, classifications, activeCharacter, damage, totalDamage, totalBuffMap) {
    updateDamage(name, classifications, activeCharacter, damage, totalDamage, totalBuffMap, 0);
}

/**
 * Updates the damage values in the substat estimator as well as the total damage distribution.
 * Has an additional 'damageMultExtra' field for any additional multipliers added on by... hardcoding.
 */
function updateDamage(name, classifications, activeCharacter, damage, totalDamage, totalBuffMap, damageMultExtra) {
    charEntries[activeCharacter]++;
    damageByCharacter[activeCharacter] += totalDamage;
    if (mode === 'Opener')
        openerDamage += totalDamage;
    else
        loopDamage += totalDamage;
    if (CHECK_STATS) {
        statCheckMap.forEach((value, stat) => {
            if (totalDamage > 0) {
                //  console.log("current stat:" + stat + " (" + value + "). attack: " + (charData[activeCharacter].attack + weaponData[activeCharacter].attack) * (1 + totalBuffMap.get('Attack') + bonusStats[activeCharacter].attack) + totalBuffMap.get('Flat Attack'));
                let currentAmount = totalBuffMap.get(stat);
                totalBuffMap.set(stat, currentAmount + value);
                var attack = (charData[activeCharacter].attack + weaponData[activeCharacter].attack) * (1 + totalBuffMap.get('Attack') + bonusStats[activeCharacter].attack) + totalBuffMap.get('Flat Attack');
                //console.log("new attack: " + attack);
                var health = (charData[activeCharacter].health) * (1 + totalBuffMap.get('Health') + bonusStats[activeCharacter].health) + totalBuffMap.get('Flat Health');
                var defense = (charData[activeCharacter].defense) * (1 + totalBuffMap.get('Defense') + bonusStats[activeCharacter].defense) + totalBuffMap.get('Flat Defense');
                var critMultiplier = (1 - Math.min(1, (charData[activeCharacter].crit + totalBuffMap.get('Crit')))) * 1 + Math.min(1, (charData[activeCharacter].crit + totalBuffMap.get('Crit'))) * (charData[activeCharacter].critDmg + totalBuffMap.get('Crit Dmg'));
                var damageMultiplier = getDamageMultiplier(classifications, totalBuffMap) + (damageMultExtra ? damageMultExtra : 0);
                var scaleFactor = classifications.includes('Df') ? defense : (classifications.includes('Hp') ? health : attack);
                var newTotalDamage = damage * scaleFactor * critMultiplier * damageMultiplier * (weaponData[activeCharacter].weapon.name === 'Nullify Damage' ? 0 : 1);
                //console.log(`damage: ${damage}; scaleFactor: ${scaleFactor}; critMult: ${critMultiplier}; damageMult: ${damageMultiplier}; weaponMult: ${(weaponData[activeCharacter].weapon.name === 'Nullify Damage' ? 0 : 1)}`)
                //console.log("new total dmg from stat: " + stat + ": " + newTotalDamage + " vs old: " + totalDamage + "; gain = " + (newTotalDamage / totalDamage - 1) + "; weapon: " + weaponData[activeCharacter].weapon.name);
                charStatGains[activeCharacter][stat] += newTotalDamage - totalDamage;
                totalBuffMap.set(stat, currentAmount); //unset the value after
            }
        });
    }

    //update damage distribution tracking chart
    for (let j = 0; j < classifications.length; j += 2) {
        let code = classifications.substring(j, j + 2);
        let key = translateClassificationCode(code);
        if (name.includes("Intro"))
            key = "Intro";
        if (name.includes("Outro"))
            key = "Outro";
        if (totalDamageMap.has(key)) {
            let currentAmount = totalDamageMap.get(key);
            totalDamageMap.set(key, currentAmount + totalDamage); // Update the total amount
            console.log("updating total damage map [" + key + "] by " + totalDamage + " (total: " + currentAmount + totalDamage + ")");
        }
        if (key === 'Intro' || key === 'Outro')
            break;
    }
}
/**
 * Gets the percentage bonus stats from the stats input.
 */
function getBonusStats(char1, char2, char3) {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Calculator');
    var range = sheet.getRange('I11:L13');
    var values = range.getValues();

    // Stats order should correspond to the columns I, J, K, L
    var statsOrder = ['attack', 'health', 'defense', 'energyRecharge'];

    // Character names - must match exactly with names in script
    var characters = [char1, char2, char3];

    var bonusStats = {};



    // Loop through each character row
    for (var i = 0; i < characters.length; i++) {
        var stats = {};
        // Loop through each stat column
        for (var j = 0; j < statsOrder.length; j++) {
            stats[statsOrder[j]] = values[i][j];
        }
        // Assign the stats object to the corresponding character
        bonusStats[characters[i]] = stats;
    }

    return bonusStats;
}

/**
 * Handles resonance energy sharing between the party for the given skillRef and value.
 */
function handleEnergyShare(value, activeCharacter) {
    characters.forEach(character => { //energy share
        let energyRecharge = (weaponData[character].mainStat === 'Energy Regen' ? weaponData[character].mainStatAmount : 0) + bonusStats[character].energyRecharge + (charData[character].bonusStats.find(element => element[0] === 'Energy Regen')?.[1] || 0);
        console.log(`adding resonance energy to ${character}; current: ${charData[character].dCond.get('Resonance')}; value = ${value}; energyRecharge = ${energyRecharge}; active multiplier: ${(character === activeCharacter ? 1 : 0.5)}`)
        charData[character].dCond.set('Resonance', charData[character].dCond.get('Resonance') + value * (1 + energyRecharge) * (character === activeCharacter ? 1 : 0.5));
    });
}


/**
 * Converts a row from the ActiveEffects sheet into an object. (Buff Object)
 * @param {Array} row A single row of data from the ActiveEffects sheet.
 * @return {Object} The row data as an object.
 */
function rowToActiveEffectObject(row) {
    var isRegularFormat = row[7] && row[7].toString().trim() !== '';
    var activator = isRegularFormat ? row[10] : row[6];
    if (skillData[row[0]] != null) {
        activator = skillData[row[0]].source;
    }
    //console.log("row: " + row + "; regular: " + isRegularFormat);
    if (isRegularFormat) {
        let triggeredByParsed = row[7];
        let parsedCondition = null;
        let parsedCondition2 = null;
        if (row[7].includes("&")) {
            triggeredByParsed = row[7].split("&")[0];
            parsedCondition2 = row[7].split("&")[1];
            console.log(`conditions for ${row[0]}; ${triggeredByParsed}, ${parsedCondition2}`);
        } else if (row[1] != 'Dmg' && row[7].includes(";")) {
            triggeredByParsed = row[7].split(";")[0];
            parsedCondition = row[7].split(";")[1];
            console.log(row[0] + "; found special condition: " + parsedCondition);
        }
        return {
            name: row[0],       // skill name
            type: row[1],        // The type of buff 
            classifications: row[2],       // The classifications this buff applies to, or All if it applies to all.
            buffType: row[3],       // The type of buff - standard, ATK buff, crit buff, elemental buff, etc
            amount: row[4],        // The value of the buff
            duration: row[5],        // How long the buff lasts - a duration is 0 indicates a passive
            active: row[6],     // Should always be TRUE
            triggeredBy: triggeredByParsed, // The Skill, or Classification type, this buff is triggered by.
            stackLimit: row[8] ? row[8] : 0, // The maximum stack limit of this buff.
            stackInterval: row[9] ? row[9] : 0, // The minimum stack interval of gaining a new stack of this buff.
            appliesTo: row[10], // The character this buff applies to, or Team in the case of a team buff
            canActivate: activator,
            availableIn: 0, //cooltime tracker for proc-based effects
            specialCondition: parsedCondition,
            additionalCondition: parsedCondition2,
            dCond: new Map([
                ['Forte', row[11] ? row[11] : 0],
                ['Concerto', row[12] ? row[12] : 0],
                ['Resonance', row[13] ? row[13] : 0]
            ])
        };
    } else { //short format for outros and similar
        return {
            name: row[0],
            type: row[1],
            classifications: row[2],
            buffType: row[3],
            amount: row[4],
            duration: row[5],
            // Assuming that for these rows, the 'active' field is not present, thus it should be assumed true
            active: true,
            triggeredBy: "", // No triggeredBy field for this format
            stackLimit: 0, // Assuming 0 as default value if not present
            stackInterval: 0, // Assuming 0 as default value if not present
            appliesTo: row[6],
            canActivate: activator,

            availableIn: 0, //cooltime tracker for proc-based effects
            specialCondition: null,
            additionalCondition: null,
            dCond: new Map([
                ['Forte', 0],
                ['Concerto', 0],
                ['Resonance', 0]
            ])
        };
    }
}

/**
 * Turns a row from "ActiveChar" - aka, the skill data -into a skill data object.
 */
function rowToActiveSkillObject(row) {
    /*if (row[0].includes("Intro") || row[0].includes("Outro")) {
      return {
        name: row[0], // + " (" + row[6] +")",
        type: row[1],
        damage: row[4],
        castTime: row[0].includes("Intro") ? 1.5 : 0,
        dps: 0,
        classifications: row[2],
        numberOfHits: 1,
        source: row[6], //the name of the character this skill belongs to
        dCond: new Map([
          ['Forte', row[7]],
          ['Concerto', 0],
          ['Resonance', 0]
        ])
      }
    } else*/
    let concerto = row[8] ? row[8] : 0;
    if (row[0].startsWith("Outro"))
        concerto = -100;
    return {
        name: row[0], // + " (" + row[6] +")",
        type: "",
        damage: row[1],
        castTime: row[2],
        dps: row[3],
        classifications: row[4],
        numberOfHits: row[5],
        source: row[6], //the name of the character this skill belongs to
        dCond: new Map([
            ['Forte', row[7] ? row[7] : 0],
            ['Concerto', concerto],
            ['Resonance', row[9] ? row[9] : 0]
        ]),
        freezeTime: row[10] ? row[10] : 0,
        cooldown: row[11] ? row[11] : 0,
        maxCharges: row[12] ? row[12] : 1
    }
}

function rowToCharacterInfo(row, levelCap) {
    const bonusTypes = [
        'Normal', 'Heavy', 'Skill', 'Liberation', 'Physical',
        'Glacio', 'Fusion', 'Electro', 'Aero', 'Spectro', 'Havoc'
    ];

    // Map bonus names to their corresponding row values
    let bonusStatsArray = bonusTypes.map((type, index) => {
        return [type, row[13 + index]]; // Row index starts at 13 for bonusNormal and increments for each bonus type
    });
    bonusStatsArray.push(['Flat Attack', row[8]]);
    bonusStatsArray.push(['Flat Health', row[9]]);
    bonusStatsArray.push(['Flat Defense', row[10]]);
    bonusStatsArray.push(['Crit', 0]);
    bonusStatsArray.push(['Crit Dmg', 0]);
    console.log(row);

    var critBase = Math.min(row[11] + 0.05, 1);
    var critDmgBase = row[12] + 1.5;
    var critBaseWeapon = 0;
    var critDmgBaseWeapon = 0;
    let build = row[7];
    let charElement = CHAR_CONSTANTS[row[1]].element;


    function updateBonusStats(array, key, value) {
        const index = array.findIndex(element => element[0] === key);
        if (index !== -1) {
            array[index][1] += value;
        }
    }
    var characterName = row[1];

    if (weaponData[characterName].mainStat === 'Crit') {
        critBaseWeapon += weaponData[characterName].mainStatAmount;
    }
    if (weaponData[characterName].mainStat === 'Crit Dmg') {
        critDmgBaseWeapon += weaponData[characterName].mainStatAmount;
    }
    let critConditional = 0;
    if (characterName === 'Changli' && row[2] >= 2)
        critConditional = 0.25;
    switch (build) {
        case "43311 (ER/ER)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 350);
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 2);
            bonusStatsArray.push(['Attack', 0.18 * 2]);
            bonusStatsArray.push(['Energy Regen', 0.32 * 2]);
            if ((critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1)
                critBase += 0.22;
            else
                critDmgBase += 0.44;
            break;
        case "43311 (Ele/Ele)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 350);
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 2);
            updateBonusStats(bonusStatsArray, charElement, 0.6 - bonusStatsArray.find(element => element[0] === charElement)[1]);
            bonusStatsArray.push(['Attack', 0.18 * 2]);
            if ((critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1)
                critBase += 0.22;
            else
                critDmgBase += 0.44;
            break;
        case "43311 (Ele/Atk)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 350);
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 2);
            updateBonusStats(bonusStatsArray, charElement, 0.3 - bonusStatsArray.find(element => element[0] === charElement)[1]);
            bonusStatsArray.push(['Attack', 0.18 * 2 + 0.3]);
            if ((critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1)
                critBase += 0.22;
            else
                critDmgBase += 0.44;
            break;
        case "43311 (Atk/Atk)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 350);
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 2);
            bonusStatsArray.push(['Attack', 0.18 * 2 + 0.6]);
            if ((critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1)
                critBase += 0.22;
            else
                critDmgBase += 0.44;
            break;
        case "44111 (Adaptive)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 300);
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 3);
            bonusStatsArray.push(['Attack', 0.18 * 3]);
            for (let i = 0; i < 2; i++) {
                console.log(`crit base: ${critBaseWeapon}; crit conditional: ${critConditional}; critDmgBase: ${critDmgBaseWeapon}`);
                if ((critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1)
                    critBase += 0.22;
                else
                    critDmgBase += 0.44;
            }
            break;
    }
    console.log(`minor fortes: ${CHAR_CONSTANTS[row[1]].minorForte1}, ${CHAR_CONSTANTS[row[1]].minorForte2}; levelcap: ${levelCap}`);
    for (var i = 0; i < bonusStatsArray.length; i++) {
        let statArray = bonusStatsArray[i];
        if (CHAR_CONSTANTS[row[1]].minorForte1 == statArray[0]) {  //unlocks at rank 2/4, aka lv50/70
            if (levelCap >= 70) {
                statArray[1] += 0.084 * (CHAR_CONSTANTS[row[1]].minorForte1 === 'Crit' ? 2 / 3 : 1);
            }
            if (levelCap >= 50) {
                statArray[1] += 0.036 * (CHAR_CONSTANTS[row[1]].minorForte1 === 'Crit' ? 2 / 3 : 1);
            }
            bonusStatsArray[i] = statArray;
        }
        if (CHAR_CONSTANTS[row[1]].minorForte2 == statArray[0]) {  //unlocks at rank 3/5, aka lv60/80
            if (levelCap >= 80) {
                statArray[1] += 0.084 * (CHAR_CONSTANTS[row[1]].minorForte2 === 'Crit' ? 2 / 3 : 1);
            }
            if (levelCap >= 60) {
                statArray[1] += 0.036 * (CHAR_CONSTANTS[row[1]].minorForte2 === 'Crit' ? 2 / 3 : 1);
            }
            bonusStatsArray[i] = statArray;
        }
    }
    console.log(`build was: ${build}; bonus stats array:`);
    console.log(bonusStatsArray);

    return {
        name: row[1],
        resonanceChain: row[2],
        weapon: row[3],
        weaponRank: row[5],
        echo: row[6],
        attack: CHAR_CONSTANTS[row[1]].baseAttack * WEAPON_MULTIPLIERS.get(levelCap)[0],
        health: CHAR_CONSTANTS[row[1]].baseHealth * WEAPON_MULTIPLIERS.get(levelCap)[0],
        defense: CHAR_CONSTANTS[row[1]].baseDef * WEAPON_MULTIPLIERS.get(levelCap)[0],
        crit: critBase,
        critDmg: critDmgBase,
        bonusStats: bonusStatsArray,
        dCond: new Map([
            ['Forte', 0],
            ['Concerto', 0],
            ['Resonance', (startFullReso ? 200 : 0)]
        ])
    }
};

function rowToCharacterConstants(row) {
    return {
        name: row[0],
        weapon: row[1],
        baseHealth: row[2],
        baseAttack: row[3],
        baseDef: row[4],
        minorForte1: row[5],
        minorForte2: row[6],
        element: row[8],
        maxForte: row[9]
    }
}

function rowToWeaponInfo(row) {
    return {
        name: row[0],
        type: row[1],
        baseAttack: row[2],
        baseMainStat: row[3],
        baseMainStatAmount: row[4],
        buff: row[5]
    }
}

/**
 * Turns a row from the "Echo" sheet into an object.
 */
function rowToEchoInfo(row) {
    return {
        name: row[0],
        damage: row[1],
        castTime: row[2],
        echoSet: row[3],
        classifications: row[4],
        numberOfHits: row[5],
        hasBuff: row[6],
        cooldown: row[7],
        dCond: new Map([
            ['Concerto', row[8] ? row[8] : 0],
            ['Resonance', row[9] ? row[9] : 0]
        ])
    }
}

/**
 * Turns a row from the "EchoBuffs" sheet into an object.
 */
function rowToEchoBuffInfo(row) {
    let triggeredByParsed = row[6];
    let parsedCondition2 = null;
    if (triggeredByParsed.includes("&")) {
        let split = triggeredByParsed.split("&");
        triggeredByParsed = split[0];
        parsedCondition2 = split[1];
        console.log(`conditions for echo buff ${row[0]}; ${triggeredByParsed}, ${parsedCondition2}`);
    }
    return {
        name: row[0],
        type: row[1],        // The type of buff 
        classifications: row[2],       // The classifications this buff applies to, or All if it applies to all.
        buffType: row[3],       // The type of buff - standard, ATK buff, crit buff, elemental buff, etc
        amount: row[4],        // The value of the buff
        duration: row[5],        // How long the buff lasts - a duration is 0 indicates a passive
        triggeredBy: triggeredByParsed, // The Skill, or Classification type, this buff is triggered by.
        stackLimit: row[7], // The maximum stack limit of this buff.
        stackInterval: row[8], // The minimum stack interval of gaining a new stack of this buff.
        appliesTo: row[9], // The character this buff applies to, or Team in the case of a team buff
        availableIn: 0, //cooltime tracker for proc-based effects
        additionalCondition: parsedCondition2
    }
}

/**
 * Creates a new echo buff object out of the given echo.
 */
function createEchoBuff(echoBuff, character) {
    var newAppliesTo = echoBuff.appliesTo === 'Self' ? character : echoBuff.appliesTo;
    return {
        name: echoBuff.name,
        type: echoBuff.type,        // The type of buff 
        classifications: echoBuff.classifications,       // The classifications this buff applies to, or All if it applies to all.
        buffType: echoBuff.buffType,       // The type of buff - standard, ATK buff, crit buff, elemental buff, etc
        amount: echoBuff.amount,        // The value of the buff
        duration: echoBuff.duration,        // How long the buff lasts - a duration is 0 indicates a passive
        triggeredBy: echoBuff.triggeredBy, // The Skill, or Classification type, this buff is triggered by.
        stackLimit: echoBuff.stackLimit, // The maximum stack limit of this buff.
        stackInterval: echoBuff.stackInterval, // The minimum stack interval of gaining a new stack of this buff.
        appliesTo: newAppliesTo, // The character this buff applies to, or Team in the case of a team buff
        canActivate: character,
        availableIn: 0, //cooltime tracker for proc-based effects
        additionalCondition: echoBuff.additionalCondition
    }
}


/**
 * Rows of WeaponBuffs raw - these have slash-delimited values in many columns.
 */
function rowToWeaponBuffRawInfo(row) {
    let triggeredByParsed = row[6];
    let parsedCondition = null;
    let parsedCondition2 = null;
    if (triggeredByParsed.includes(";")) {
        triggeredByParsed = row[6].split(";")[0];
        parsedCondition = row[6].split(";")[1];
        console.log(`found a special condition for ${row[0]}: ${parsedCondition}`);
    }
    if (triggeredByParsed.includes("&")) {
        let split = triggeredByParsed.split("&");
        triggeredByParsed = split[0];
        parsedCondition2 = split[1];
        console.log(`conditions for weapon buff ${row[0]}; ${triggeredByParsed}, ${parsedCondition2}`);
    }
    return {
        name: row[0],       // buff  name
        type: row[1],        // the type of buff 
        classifications: row[2],       // the classifications this buff applies to, or All if it applies to all.
        buffType: row[3],       // the type of buff - standard, ATK buff, crit buff, deepen, etc
        amount: row[4],        // slash delimited - the value of the buff
        duration: row[5],        // slash delimited - how long the buff lasts - a duration is 0 indicates a passive. for BuffEnergy, this is the Cd between procs
        triggeredBy: triggeredByParsed, // The Skill, or Classification type, this buff is triggered by.
        stackLimit: row[7], // slash delimited - the maximum stack limit of this buff.
        stackInterval: row[8], // slash delimited - the minimum stack interval of gaining a new stack of this buff.
        appliesTo: row[9], // The character this buff applies to, or Team in the case of a team buff
        availableIn: 0, //cooltime tracker for proc-based effects
        specialCondition: parsedCondition,
        additionalCondition: parsedCondition2
    }
}

/**
 * A refined version of a weapon buff specific to a character and their weapon rank.
 */
function rowToWeaponBuff(weaponBuff, rank, character) {
    console.log(`weapon buff: ${weaponBuff}; amount: ${weaponBuff.amount}`);
    var newAmount = weaponBuff.amount.includes('/') ? weaponBuff.amount.split('/')[rank] : weaponBuff.amount;
    var newDuration = weaponBuff.duration.includes('/') ? weaponBuff.duration.split('/')[rank] : weaponBuff.duration;
    var newStackLimit = ("" + weaponBuff.stackLimit).includes('/') ? weaponBuff.stackLimit.split('/')[rank] : weaponBuff.stackLimit;
    var newStackInterval = ("" + weaponBuff.stackInterval).includes('/') ? weaponBuff.stackInterval.split('/')[rank] : weaponBuff.stackInterval;
    var newAppliesTo = weaponBuff.appliesTo === 'Self' ? character : weaponBuff.appliesTo;
    return {
        name: weaponBuff.name,       // buff  name
        type: weaponBuff.type,        // the type of buff 
        classifications: weaponBuff.classifications,       // the classifications this buff applies to, or All if it applies to all.
        buffType: weaponBuff.buffType,       // the type of buff - standard, ATK buff, crit buff, deepen, etc
        amount: parseFloat(newAmount),        // slash delimited - the value of the buff
        active: true,
        duration: (weaponBuff.duration === 'Passive' || weaponBuff.duration === 0) ? 'Passive' : parseFloat(newDuration),        // slash delimited - how long the buff lasts - a duration is 0 indicates a passive
        triggeredBy: weaponBuff.triggeredBy, // The Skill, or Classification type, this buff is triggered by.
        stackLimit: parseFloat(newStackLimit), // slash delimited - the maximum stack limit of this buff.
        stackInterval: parseFloat(newStackInterval), // slash delimited - the minimum stack interval of gaining a new stack of this buff.
        appliesTo: newAppliesTo, // The character this buff applies to, or Team in the case of a team buff
        canActivate: character,
        availableIn: 0, //cooltime tracker for proc-based effects
        specialCondition: weaponBuff.specialCondition,
        additionalCondition: weaponBuff.additionalCondition
    }
}

/**
 * A character weapon object.
 */
function characterWeapon(pWeapon, pLevelCap, pRank) {
    return {
        weapon: pWeapon,
        attack: pWeapon.baseAttack * WEAPON_MULTIPLIERS.get(pLevelCap)[0],
        mainStat: pWeapon.baseMainStat,
        mainStatAmount: pWeapon.baseMainStatAmount * WEAPON_MULTIPLIERS.get(pLevelCap)[1],
        rank: pRank - 1
    }
}

function createActiveBuff(pBuff, pTime) {
    return {
        buff: pBuff,
        startTime: pTime,
        stacks: 0,
        stackTime: 0
    }
}

function createActiveStackingBuff(pBuff, time, pStacks) {
    return {
        buff: pBuff,
        startTime: time,
        stacks: pStacks,
        stackTime: time
    }
}

/**
 * Creates a passive damage instance that's actively procced by certain attacks.
 */
class PassiveDamage {
    constructor(name, classifications, type, damage, duration, startTime, limit, interval, triggeredBy, owner, slot, dCond) {
        this.name = name;
        this.classifications = classifications;
        this.type = type;
        this.damage = damage;
        this.duration = duration;
        this.startTime = startTime;
        this.limit = limit;
        this.interval = interval;
        this.triggeredBy = triggeredBy.split(';')[1];
        this.owner = owner;
        this.slot = slot;
        this.lastProc = -999;
        this.numProcs = 0;
        this.procMultiplier = 1;
        this.totalDamage = 0;
        this.totalBuffMap = [];
        this.proccableBuffs = [];
        this.dCond = dCond;
        this.activated = false; //an activation flag for TickOverTime-based effects
        this.remove = false; //a flag for if a passive damage instance needs to be removed (e.g. when a new instance is added)
    }

    addBuff(buff) {
        console.log(`adding ${buff.buff.name} as a proccable buff to ${this.name}`);
        console.log(buff);
        this.proccableBuffs.push(buff);
    }

    /**
     * Handles and updates the current proc time according to the skill reference info.
     */
    handleProcs(currentTime, castTime, numberOfHits) {
        let procs = 0;
        let timeBetweenHits = castTime / (numberOfHits > 1 ? numberOfHits - 1 : 1);
        console.log(`handleProcs called with currentTime: ${currentTime}, castTime: ${castTime}, numberOfHits: ${numberOfHits}; type: ${this.type}`);
        console.log(`lastProc: ${this.lastProc}, interval: ${this.interval}, timeBetweenHits: ${timeBetweenHits}`);
        this.activated = true;
        if (this.interval > 0) {
            if (this.type === 'TickOverTime') {
                for (let time = (this.lastProc < 0 ? currentTime : (this.lastProc + this.interval)); time <= currentTime; time += this.interval) {
                    procs++;
                    this.lastProc = time;
                    console.log(`Proc occurred at hitTime: ${time}`);
                }
            } else {
                for (let hitIndex = 0; hitIndex < numberOfHits; hitIndex++) {
                    let hitTime = currentTime + timeBetweenHits * hitIndex;
                    //console.log(`Checking hitIndex ${hitIndex}: hitTime: ${hitTime}, lastProc + interval: ${this.lastProc + this.interval}`);
                    if (hitTime - this.lastProc >= this.interval) {
                        procs++;
                        this.lastProc = hitTime;
                        console.log(`Proc occurred at hitTime: ${hitTime}`);
                    }
                }
            }
        } else {
            procs = numberOfHits;
        }
        if (this.limit > 0)
            procs = Math.min(procs, this.limit - this.numProcs);
        this.numProcs += procs;
        this.procMultiplier = procs;
        console.log(`Total procs this time: ${procs}`);
        if (procs > 0) {
            this.proccableBuffs.forEach(buff => {
                let buffObject = buff.buff;
                if (buffObject.type === 'StackingBuff') {
                    var stacksToAdd = 1;
                    var stackMult = 1 + (buffObject.triggeredBy.includes('Passive') && buffObject.name.startsWith('Incandescence') ? 1 : 0);
                    let effectiveInterval = buffObject.stackInterval;
                    if (buffObject.name.startsWith('Incandescence') && jinhsiOutroActive) {
                        effectiveInterval = 1;
                    }
                    if (effectiveInterval < castTime) { //potentially add multiple stacks
                        let maxStacksByTime = (effectiveInterval == 0 ? numberOfHits : Math.floor(castTime / effectiveInterval));
                        stacksToAdd = Math.min(maxStacksByTime, numberOfHits);
                    }
                    console.log("stacking buff " + buffObject.name + " is procced; " + buffObject.triggeredBy + "; stacks: " + buff.stacks + "; toAdd: " + stacksToAdd + "; mult: " + stackMult + "; target stacks: " + (Math.min((stacksToAdd * stackMult), buffObject.stackLimit)) + "; interval: " + effectiveInterval);
                    buff.stacks = Math.min(stacksToAdd * stackMult, buffObject.stackLimit);
                    buff.stackTime = this.lastProc;
                }
                buff.startTime = this.lastProc;
                queuedBuffs.push(buff);
            });
        }
        return procs;
    }

    canRemove(currentTime, removeBuff) {
        return this.numProcs >= this.limit && this.limit > 0 || (currentTime - this.startTime > this.duration) || (removeBuff && this.name.includes(removeBuff)) || this.remove;
    }

    canProc(currentTime, skillRef) {
        console.log("can it proc? CT: " + currentTime + "; lastProc: " + this.lastProc + "; interval: " + this.interval);
        return (currentTime + skillRef.castTime - this.lastProc >= this.interval - .01);
    }

    /**
     * Updates the total buff map to the latest local buffs.
     */
    updateTotalBuffMap() {
        if (lastTotalBuffMap[this.owner])
            this.setTotalBuffMap(lastTotalBuffMap[this.owner]);
        else
            console.log("undefined lastTotalBuffMap");
    }

    /**
     * Sets the total buff map, updating with any skill-specific buffs.
     */
    setTotalBuffMap(totalBuffMap) {
        this.totalBuffMap = new Map(totalBuffMap);

        //these may have been set from the skill proccing it
        this.totalBuffMap.set('Specific', 0);
        this.totalBuffMap.set('Deepen', 0);
        this.totalBuffMap.set('Multiplier', 0);

        this.totalBuffMap.forEach((value, stat) => {
            if (stat.includes(this.name)) {
                if (stat.includes('Specific')) {
                    let current = this.totalBuffMap.get('Specific');
                    this.totalBuffMap.set('Specific', current + value);
                    console.log(`updating damage bonus for ${this.name} to ${current} + ${value}`);
                } else if (stat.includes('Multiplier')) {
                    let current = this.totalBuffMap.get('Multiplier');
                    this.totalBuffMap.set('Multiplier', current + value);
                    console.log(`updating damage multiplier for ${this.name} to ${current} + ${value}`);
                } else if (stat.includes('Deepen')) {
                    let element = reverseTranslateClassificationCode(stat.split('(')[0].trim());
                    if (this.classifications.includes(element)) {
                        let current = this.totalBuffMap.get('Deepen');
                        this.totalBuffMap.set('Deepen', current + value);
                        console.log(`updating damage Deepen for ${this.name} to ${current} + ${value}`);
                    }
                }
            }
        });

        //the tech to apply buffs like this to passive damage effects would be a 99% unnecessary loop so i'm hardcoding this (for now) surely it's not more than a case or two
        if (this.name.includes("Marcato") && sequences['Mortefi'] >= 3) {
            this.totalBuffMap.set('Crit Dmg', this.totalBuffMap.get('Crit Dmg') + 0.3);
        }
    }

    checkProcConditions(skillRef) {
        console.log("checking proc conditions with skill: [" + this.triggeredBy + "] vs " + skillRef.name);
        console.log(skillRef);
        if (!this.triggeredBy)
            return false;
        if ((this.activated && this.type === 'TickOverTime') || this.triggeredBy === 'Any' || (this.triggeredBy.length > 2 && (this.triggeredBy.includes(skillRef.name) || skillRef.name.includes(this.triggeredBy))) || (this.triggeredBy.length == 2 && skillRef.classifications.includes(this.triggeredBy)))
            return true;
        var triggeredByConditions = this.triggeredBy.split(',');
        triggeredByConditions.forEach(condition => {
            console.log(`checking condition: ${condition}; skill ref classifications: ${skillRef.classifications}; name: ${skillRef.name}`);
            if ((condition.length == 2 && skillRef.classifications.includes(condition)) || (condition.length > 2 && (skillRef.name.includes(condition) || condition.includes(skillRef.name))))
                return true;
        });
        console.log("failed match");
        return false;
    }

    /**
     * Calculates a proc's damage, and adds it to the total. Also adds any relevant dynamic conditions.
     */
    calculateProc(activeCharacter) {
        if (this.dCond != null) {
            this.dCond.forEach((value, condition) => {
                if (value > 0) {
                    console.log(`[PASSIVE DAMAGE] evaluating dynamic condition for ${this.name}: ${condition} x${value}`);
                    if (condition === 'Resonance')
                        handleEnergyShare(value, activeCharacter);
                    else
                        charData[activeCharacter].dCond.set(condition, charData[activeCharacter].dCond.get(condition) + value);
                }
            });
        }

        let bonusAttack = 0;
        /*if (activeCharacter != this.owner) {
          if (charData[this.owner].weapon.includes("Stringmaster")) { //sorry... hardcoding just this once
            bonusAttack = .12 + weaponData[this.owner].rank * 0.03;        
          }
        }*/
        let extraMultiplier = 0;
        let extraCritDmg = 0;
        if (this.name.includes("Marcato")) {
            extraMultiplier += rythmicVibrato * 0.015;
            //console.log(`rythmic vibrato count: ${rythmicVibrato}`);
        }

        let totalBuffMap = this.totalBuffMap;
        let attack = (charData[this.owner].attack + weaponData[this.owner].attack) * (1 + totalBuffMap.get('Attack') + bonusStats[this.owner].attack + bonusAttack) + totalBuffMap.get('Flat Attack');
        let health = (charData[this.owner].health) * (1 + totalBuffMap.get('Health') + bonusStats[this.owner].health) + totalBuffMap.get('Flat Health');
        let defense = (charData[this.owner].defense) * (1 + totalBuffMap.get('Defense') + bonusStats[this.owner].defense) + totalBuffMap.get('Flat Defense');
        let critMultiplier = (1 - Math.min(1, (charData[this.owner].crit + totalBuffMap.get('Crit')))) * 1 + Math.min(1, (charData[this.owner].crit + totalBuffMap.get('Crit'))) * (charData[this.owner].critDmg + totalBuffMap.get('Crit Dmg') + extraCritDmg);
        let damageMultiplier = getDamageMultiplier(this.classifications, totalBuffMap) + extraMultiplier;


        let additiveValueKey = `${this.name} (Additive)`;
        let rawDamage = this.damage * (this.name.startsWith("Jué") ? 1 : skillLevelMultiplier) + (totalBuffMap.has(additiveValueKey) ? totalBuffMap.get(additiveValueKey) : 0);

        //console.log(`${rawDamage} / ${additiveValueKey}:  ${totalBuffMap.has(additiveValueKey)} / ${totalBuffMap.has(additiveValueKey) ? totalBuffMap.get(additiveValueKey) : 0}`);

        let scaleFactor = this.classifications.includes('Df') ? defense : (this.classifications.includes('Hp') ? health : attack);
        let totalDamage = rawDamage * scaleFactor * critMultiplier * damageMultiplier * (weaponData[this.owner].weapon.name === 'Nullify Damage' ? 0 : 1);
        console.log(`passive proc damage: ${rawDamage.toFixed(2)}; attack: ${(charData[this.owner].attack + weaponData[this.owner].attack).toFixed(2)} x ${(1 + totalBuffMap.get('Attack') + bonusStats[this.owner].attack).toFixed(2)}; crit mult: ${critMultiplier.toFixed(2)}; dmg mult: ${damageMultiplier.toFixed(2)}; total dmg: ${totalDamage.toFixed(2)}`);
        this.totalDamage += totalDamage * this.procMultiplier;
        updateDamage(this.name, this.classifications, this.owner, rawDamage * this.procMultiplier, totalDamage * this.procMultiplier, totalBuffMap, extraMultiplier);
        this.procMultiplier = 1;
        return totalDamage;
    }

    /**
     * Returns a note to place on the cell.
     */
    getNote() {
        let additiveValueKey = `${this.name} (Additive)`;
        if (this.limit == 1) {
            if (this.name === 'Star Glamour' && sequences['Jinhsi'] >= 2) //todo...
                return `This skill triggered an additional damage effect: ${this.name}, dealing ${this.totalDamage.toFixed(2)} DMG (Base Ratio: ${(this.damage * 100).toFixed(2)}%  x ${skillLevelMultiplier.toFixed(2)} + ${(this.totalBuffMap.has(additiveValueKey) ? this.totalBuffMap.get(additiveValueKey) * 100 : 0)}%).`;
            else
                return `This skill triggered an additional damage effect: ${this.name}, dealing ${this.totalDamage.toFixed(2)} DMG (Base Ratio: ${(this.damage * 100).toFixed(2)}%  x ${skillLevelMultiplier.toFixed(2)} + ${(this.totalBuffMap.has(additiveValueKey) ? this.totalBuffMap.get(additiveValueKey) * 100 : 0)}%).`;
        } else {
            if (this.type === 'TickOverTime') {
                if (this.name.startsWith("Jué"))
                    return `This skill triggered a passive DOT effect: ${this.name}, which has ticked ${this.numProcs} times for ${this.totalDamage.toFixed(2)} DMG in total (Base Ratio: ${(this.damage * 100).toFixed(2)}% + ${(this.totalBuffMap.has(additiveValueKey) ? this.totalBuffMap.get(additiveValueKey) * 100 : 0).toFixed(2)}%).`;
                else
                    return `This skill triggered a passive DOT effect: ${this.name}, which has ticked ${this.numProcs} times for ${this.totalDamage.toFixed(2)} DMG in total (Base Ratio: ${(this.damage * 100).toFixed(2)}% x ${skillLevelMultiplier.toFixed(2)} + ${(this.totalBuffMap.has(additiveValueKey) ? this.totalBuffMap.get(additiveValueKey) * 100 : 0).toFixed(2)}%).`;
            } else {
                return `This skill triggered a passive damage effect: ${this.name}, which has procced ${this.numProcs} times for ${this.totalDamage.toFixed(2)} DMG in total (Base Ratio: ${(this.damage * 100).toFixed(2)}% x ${skillLevelMultiplier.toFixed(2)} + ${(this.totalBuffMap.has(additiveValueKey) ? this.totalBuffMap.get(additiveValueKey) * 100 : 0).toFixed(2)}%).`;
            }
        }
    }
}


/**
 * Extracts the skill reference from the skillData object provided, with the name of the current character.
 * Skill data objects have a (Character) name at the end of them to avoid duplicates. Jk, now they don't, but all names MUST be unique.
 */
function getSkillReference(skillData, name, character) {
    return skillData[name/* + " (" + character + ")"*/];
}

function extractNumberAfterX(inputString) {
    var match = inputString.match(/x(\d+)/);
    return match ? parseInt(match[1], 10) : null;
}

function reverseTranslateClassificationCode(code) {
    const classifications = {
        'Normal': 'No',
        'Heavy': 'He',
        'Skill': 'Sk',
        'Liberation': 'Rl',
        'Glacio': 'Gl',
        'Spectro': 'Sp',
        'Fusion': 'Fu',
        'Electro': 'El',
        'Aero': 'Ae',
        'Spectro': 'Sp',
        'Havoc': 'Ha',
        'Physical': 'Ph',
        'Echo': 'Ec',
        'Outro': 'Ou',
        'Intro': 'In'
    };
    return classifications[code] || code; // Default to code if not found
}

function translateClassificationCode(code) {
    const classifications = {
        'No': 'Normal',
        'He': 'Heavy',
        'Sk': 'Skill',
        'Rl': 'Liberation',
        'Gl': 'Glacio',
        'Sp': 'Spectro',
        'Fu': 'Fusion',
        'El': 'Electro',
        'Ae': 'Aero',
        'Sp': 'Spectro',
        'Ha': 'Havoc',
        'Ph': 'Physical',
        'Ec': 'Echo',
        'Ou': 'Outro',
        'In': 'Intro'
    };
    return classifications[code] || code; // Default to code if not found
}

function getDamageMultiplier(classification, totalBuffMap) {
    let damageMultiplier = 1;
    let damageBonus = 1;
    let damageDeepen = 0;
    let enemyDefense = 792 + 8 * enemyLevel;
    let defPen = totalBuffMap.get('Ignore Defense');
    let defenseMultiplier = (800 + levelCap * 8) / (enemyDefense * (1 - defPen) + 800 + levelCap * 8);
    //console.log(`defenseMultiplier: ${defenseMultiplier}`);
    let resShred = totalBuffMap.get('Resistance');
    // loop through each pair of characters in the classification string
    for (let i = 0; i < classification.length; i += 2) {
        let code = classification.substring(i, i + 2);
        let classificationName = translateClassificationCode(code);
        // if classification is in the totalBuffMap, apply its buff amount to the damage multiplier
        if (totalBuffMap.has(classificationName)) {
            if (STANDARD_BUFF_TYPES.includes(classificationName)) { //check for deepen effects as well
                let deepenName = classificationName + " (Deepen)";
                if (totalBuffMap.has(deepenName))
                    damageDeepen += totalBuffMap.get(deepenName);
                damageBonus += totalBuffMap.get(classificationName);
            } else {
                damageBonus += totalBuffMap.get(classificationName);
            }
        }
    }
    let resMultiplier = 1;
    if (res <= 0) { //resistance multiplier calculation
        resMultiplier = 1 - (res - resShred) / 2;
    } else if (res < .8) {
        resMultiplier = 1 - (res - resShred);
    } else {
        resMultiplier = 1 / (1 + (res - resShred) * 5);
    }
    //console.log("res multiplier: " + resMultiplier);
    damageDeepen += totalBuffMap.get('Deepen');
    damageBonus += totalBuffMap.get('Specific');
    console.log(`damage multiplier: (BONUS=${damageBonus}) * (MULTIPLIER=1 + ${totalBuffMap.get('Multiplier')}) * (DEEPEN=1 + ${damageDeepen}) * (RES=${resMultiplier}) * (DEF=${defenseMultiplier})`);
    return damageMultiplier * damageBonus * (1 + totalBuffMap.get('Multiplier')) * (1 + damageDeepen) * resMultiplier * defenseMultiplier;
}

/**
 * Loads skills from the calculator "ActiveChar" sheet.
 */
function getSkills() {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('ActiveChar');
    var range = sheet.getDataRange();
    var values = range.getValues();

    // filter rows where the first cell is not empty
    var filteredValues = values.filter(function (row) {
        return row[0].toString().trim() !== ''; // Ensure that the name is not empty
    });

    var objects = filteredValues.map(rowToActiveSkillObject);
    return objects;
}

function getActiveEffects() {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('ActiveEffects');
    var range = sheet.getDataRange();
    var values = range.getValues();

    var objects = values.map(rowToActiveEffectObject).filter(effect => effect !== null);
    return objects;
}

function getWeapons() {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Weapons');
    var range = sheet.getDataRange();
    var values = range.getValues();

    var weaponsMap = {};

    // Start loop at 1 to skip header row
    for (var i = 1; i < values.length; i++) {
        if (values[i][0]) { // Check if the row actually contains a weapon name
            var weaponInfo = rowToWeaponInfo(values[i]);
            weaponsMap[weaponInfo.name] = weaponInfo; // Use weapon name as the key for lookup
        }
    }

    return weaponsMap;
}

function getEchoes() {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Echo');
    var range = sheet.getDataRange();
    var values = range.getValues();

    var echoMap = {};

    for (var i = 1; i < values.length; i++) {
        if (values[i][0]) { // check if the row actually contains an echo name
            var echoInfo = rowToEchoInfo(values[i]);
            echoMap[echoInfo.name] = echoInfo; // Use echo name as the key for lookup
        }
    }

    return echoMap;
}


function getCharacterConstants() {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Constants');
    var range = sheet.getDataRange();
    var values = range.getValues();
    var charConstants = {};

    for (var i = 3; i < values.length; i++) {
        if (values[i][0] && values[i][0] != '') { // check if the row actually contains a name
            var charInfo = rowToCharacterConstants(values[i]);
            charConstants[charInfo.name] = charInfo; // use weapon name as the key for lookup
        } else {
            break;
        }
    }

    return charConstants;
}

/**
 * Exports the build.
 * Format:
 * Friendly Name; CSV Stats & Bonus Stats; Stats 2; Stats 3; CSV Rotation (Format: Character&Skill)
 * 
 * Example:
 * S1R1 Jinhsi + Ages of Harvest / ... ; 100,0,0,43%,81%,...; [x3] Jinshi&Skill: Test,Jinshi&Basic: Test2
 */
function exportBuild() {
    var characters = [];
    var charInfo = [];
    var charInfoRaw = [];
    var bonusStats = [];
    var buildString = '';
    for (let i = 7; i <= 9; i++) {
        let character = rotationSheet.getRange(`B${i}`).getValue();
        characters.push(character);
        charInfo.push(rowToCharacterInfoRaw(rotationSheet.getRange(`A${i}:Z${i}`).getValues()[0]));
        charInfoRaw.push(rotationSheet.getRange(`B${i}:Z${i}`).getValues()[0]);
        bonusStats.push(rotationSheet.getRange(`I${i + 4}:L${i + 4}`).getValues()[0]);
    }
    var divider = '';
    for (let i = 0; i < characters.length; i++) {
        buildString += divider;
        buildString += 'S';
        buildString += charInfo[i].resonanceChain;
        buildString += 'R';
        buildString += charInfo[i].weaponRank;
        buildString += ' ';
        buildString += characters[i];
        buildString += ' + ';
        buildString += charInfo[i].weapon;
        divider = ' / ';
    }
    buildString += ';';
    var divider2 = '';
    for (let i = 0; i < characters.length; i++) {
        buildString += divider2;
        divider = '';
        for (let j = 0; j < charInfoRaw[i].length; j++) {
            buildString += divider;
            buildString += charInfoRaw[i][j];
            divider = ',';
        }
        for (let j = 0; j < bonusStats[i].length; j++) {
            buildString += divider;
            buildString += bonusStats[i][j];
            divider = ',';
        }
        divider2 = ';';
    }
    buildString += ';';

    divider = '';
    for (let i = ROTATION_START; i <= ROTATION_END; i++) {
        let character = rotationSheet.getRange('A' + i).getValue();
        let skill = rotationSheet.getRange('B' + i).getValue();
        if (!character || !skill)
            break;
        buildString += divider;
        buildString += character;
        buildString += '&';
        buildString += skill;
        divider = ',';
    }
    rotationSheet.getRange('K23').setValue(buildString);

    //save the previous execution to the first open slot
    if (rotationSheet.getRange('H28').getValue() > 0) {
        var library = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Build Library');
        for (let i = 10; i < 1000; i++) {
            if (library.getRange(`M${i}`).getValue()) {
                continue;
            }
            let data = [
                [
                    characters[0],
                    characters[1],
                    characters[2],
                    rotationSheet.getRange('H27').getValue(),
                    rotationSheet.getRange('H28').getValue(),
                    rotationSheet.getRange('H29').getValue(),
                    buildString
                ]
            ];

            let rowRange = library.getRange(`M${i}:S${i}`);
            rowRange.setValues(data);
            break;
        }
    }
}

/**
 * Turns a row into a raw character data info for build exporting.
 */
function rowToCharacterInfoRaw(row) {
    return {
        name: row[1],
        resonanceChain: row[2],
        weapon: row[3],
        weaponRank: row[5],
        echo: row[6],
        build: row[7],
        attack: row[8],
        health: row[9],
        defense: row[10],
        crit: row[11],
        critDmg: row[12],
        normal: row[13],
        heavy: row[14],
        skill: row[15],
        liberation: row[16]
    }
}


function test() {
    var effects = getActiveEffects();
    effects.forEach(effect => {
        Logger.log("Name: " + effect.name +
            ", Type: " + effect.type +
            ", Classifications: " + effect.classifications +
            ", Buff Type: " + effect.buffType +
            ", Amount: " + effect.amount +
            ", Duration: " + effect.duration +
            ", Active: " + effect.active +
            ", Triggered By: " + effect.triggeredBy +
            ", Stack Limit: " + effect.stackLimit +
            ", Stack Interval: " + effect.stackInterval
        );
    });
}
