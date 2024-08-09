# Wuwa DPS Calculator Script
# original in JavaScript by @Maygi
# modified by @HikariTenshi

# This is the script attached to the Wuwa DPS Calculator. Running this is required to update
# all the calculations. Adjust the CHECK_STATS flag if you'd like it to run the Substat checking
# logic (to calculate which substats are the most effective). This is toggleable because this
# causes a considerable runtime increase.

import logging
from copy import deepcopy
from functools import cmp_to_key

VERSION = "V3.3.1"

CHECK_STATS = True

STANDARD_BUFF_TYPES = ["Normal", "Heavy", "Skill", "Liberation"]
ELEMENTAL_BUFF_TYPES = ["Glacio", "Fusion", "Electro", "Aero", "Spectro", "Havoc"]
WEAPON_MULTIPLIERS = { # TODO fix this duplicate to pull from database
    1: [1, 1],
    20: [2.59, 1.78],
    40: [5.03, 2.56],
    50: [6.62, 2.94],
    60: [8.24, 3.33],
    70: [9.47, 3.72],
    80: [11.15, 4.11],
    90: [12.5, 4.5]
}

def getCharacterConstants(): # TODO change this to use databases instead
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Constants")
    range = sheet.getDataRange()
    values = range.getValues()
    charConstants = {}

    for i in range(3, len(values)):
        if values[i][0] and values[i][0] != "": # check if the row actually contains a name
            charInfo = rowToCharacterConstants(values[i])
            charConstants[charInfo["name"]] = charInfo # use weapon name as the key for lookup
        else:
            break

    return charConstants

CHAR_CONSTANTS = getCharacterConstants()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

skillData = []
passiveDamageInstances = []
weaponData = {}
charData = {}
characters = []
sequences = []
lastTotalBuffMap = {} # the last updated total buff maps for each character
bonusStats = []
queuedBuffs = []
# TODO change this to use databases instead
sheet = SpreadsheetApp.getActiveSpreadsheet()
rotationSheet = sheet.getSheetByName("Calculator")
skillLevelMultiplier = rotationSheet.getRange("AH5").getValue()

# The "Opener" damage is the total damage dealt before the first main DPS (first character) executes their Outro for the first time.
openerDamage = 0
openerTime = 0
loopDamage = 0
mode = "Opener"

# TODO remove these since these are spreadsheet specific
ROTATION_START = 34
ROTATION_END = 145

jinhsiOutroActive = False
rythmicVibrato = 0

startFullReso = False

# Data for stat analysis
statCheckMap = { # TODO check whether this is a duplicate to be replaced with databases
    "Attack": .086,
    "Health": .086,
    "Defense": .109,
    "Crit": .081,
    "Crit Dmg": .162,
    "Normal": .086,
    "Heavy": .086,
    "Skill": .086,
    "Liberation": .086,
    "Flat Attack": 40
}
charStatGains = {}
charEntries = {}
totalDamageMap = { # TODO check whether this is a duplicate to be replaced with databases
    "Normal": 0,
    "Heavy": 0,
    "Skill": 0,
    "Liberation": 0,
    "Intro": 0,
    "Outro": 0,
    "Echo": 0
}
damageByCharacter = {}

# The main method that runs all the calculations and updates the data.
# Yes, I know, it's like an 800 line method, so ugly.

def runCalculations():
    # TODO change these to databases
    character1 = rotationSheet.getRange("B7").getValue()
    character2 = rotationSheet.getRange("B8").getValue()
    character3 = rotationSheet.getRange("B9").getValue()
    levelCap = rotationSheet.getRange("F4").getValue()
    oldDamage = rotationSheet.getRange("G32").getValue()
    startFullReso = rotationSheet.getRange("D4").getValue()
    activeBuffs = {}
    characters = [character1, character2, character3]
    activeBuffs["Team"] = set()
    activeBuffs[character1] = set()
    activeBuffs[character2] = set()
    activeBuffs[character3] = set()

    lastSeen = {}
    rotationSheet.getRange("H26").setValue(oldDamage)

    initialDCond = {}
    cooldownMap = {}

    charData = {}

    bonusStats = getBonusStats(character1, character2, character3)

    for j in range(characters.length):
        damageByCharacter[characters[j]] = 0
        charEntries[characters[j]] = 0
        charStatGains[characters[j]] = {
            "Attack": 0,
            "Health": 0,
            "Defense": 0,
            "Crit": 0,
            "Crit Dmg": 0,
            "Normal": 0,
            "Heavy": 0,
            "Skill": 0,
            "Liberation": 0,
            "Flat Attack": 0
        }
    # logger.info(charStatGains)

    weaponData = {}
    weapons = getWeapons()

    # TODO change this to use databases instead
    charactersWeaponsRange = rotationSheet.getRange("D7:D9").getValues()
    weaponRankRange = rotationSheet.getRange("F7:F9").getValues()

    # load echo data into the echo parameter
    echoes = getEchoes()

    for i in range(characters.length):
        weaponData[characters[i]] = characterWeapon(weapons[charactersWeaponsRange[i][0]], levelCap, weaponRankRange[i][0])
        charData[characters[i]] = rowToCharacterInfo(rotationSheet.getRange(f'A{7 + i}:Z{7 + i}').getValues()[0], levelCap)
        sequences[characters[i]] = charData[characters[i]]["resonanceChain"]

        echoName = charData[characters[i]]["echo"]
        charData[characters[i]]["echo"] = echoes[echoName]
        skillData[echoName] = charData[characters[i]]["echo"]
        logger.info(f'setting skill data for echo {echoName}; echo cd is {charData[characters[i]]["echo"]["cooldown"]}')
        initialDCond[characters[i]] = {
            ["Forte", 0],
            ["Concerto", 0],
            ["Resonance", 0]
        }
        lastSeen[characters[i]] = -1

    skillData = {}
    effectObjects = getSkills()
    for effect in effectObjects:
        skillData[effect["name"]] = effect

    # logger.info(activeBuffs)
    trackedBuffs = [] # Stores the active buffs for each time point.
    # TODO change this to use databases instead
    dataCellCol = "F"
    dataCellColTeam = "G"
    dataCellColDmg = "H"
    dataCellColResults = "I"
    dataCellRowResults = ROTATION_END + 3
    dataCellColNextSub = "I"
    dataCellRowNextSub = 18
    dataCellColDCond = "M"
    dataCellRowDCond = ROTATION_END + 4
    dataCellTime = "AH"

    # Outro buffs are special, and are saved to be applied to the NEXT character swapped into.
    queuedBuffsForNext = []
    lastCharacter = None

    swapped = False
    allBuffs = getActiveEffects() # retrieves all buffs "in play" from the ActiveEffects table.

    weaponBuffsRange = sheet.getSheetByName("WeaponBuffs").getRange("A2:K500").getValues()
    weaponBuffsRange = [row for row in weaponBuffsRange if row[0].strip() != ""] # Ensure that the name is not empty
    weaponBuffData = [rowToWeaponBuffRawInfo(row) for row in weaponBuffsRange]

    echoBuffsRange = sheet.getSheetByName("EchoBuffs").getRange("A2:K500").getValues().filter
    echoBuffsRange = [row for row in echoBuffsRange if row[0].strip() != ""] # Ensure that the name is not empty
    echoBuffData = [rowToEchoBuffInfo(row) for row in echoBuffsRange]

    for i in range(3): # loop through characters and add buff data if applicable
        for echoBuff in echoBuffData:
            if (charData[characters[i]]["echo"]["name"] in echoBuff["name"] or 
            charData[characters[i]]["echo"]["echoSet"] in echoBuff["name"]):
                newBuff = createEchoBuff(echoBuff, characters[i])
                allBuffs.append(newBuff)
                logger.info(f'adding echo buff {echoBuff["name"]} to {characters[i]}')
                logger.info(newBuff)

        for weaponBuff in weaponBuffData:
            if weaponData[characters[i]]["weapon"]["buff"] in weaponBuff["name"]:
                newBuff = rowToWeaponBuff(weaponBuff, weaponData[characters[i]].rank, characters[i])
                logger.info(f'adding weapon buff {newBuff["name"]} to {characters[i]}')
                allBuffs.append(newBuff);

    # apply passive buffs
    for i in range(len(allBuffs) - 1, -1, -1):
        buff = allBuffs[i]
        if ((buff["triggeredBy"] == "Passive" and buff["type"] == "Buff") or buff["duration"] == "Passive") and buff["specialCondition"] is None:
            buff["duration"] = 9999
            logger.info(f'buff {buff["name"]} applies to: {buff["appliesTo"]}')
            activeBuffs[buff["appliesTo"]].add(createActiveBuff(buff, 0))
            logger.info(f'adding passive buff : {buff["name"]} to {buff["appliesTo"]}')

            allBuffs.pop(i) # remove passive buffs from the list afterwards

    #TODO move this function outside
    # Buff sorting - damage effects need to always be defined first so if other buffs exist that can be procced by them, then they can be added to the "proccable" list.
    # Buffs that have "Buff:" conditions need to be last, as they evaluate the presence of buffs.
    def compareBuffs(a, b):
        # If a.type is "Dmg" and b.type is not, a comes first
        if (a['type'] == "Dmg" or "Hl" in a["classifications"]) and (b["type"] != "Dmg" and "Hl" not in b["classifications"]):
            return -1
        # If b.type is "Dmg" and a.type is not, b comes first
        elif (a["type"] != "Dmg" and "Hl" not in a["classifications"]) and (b["type"] == "Dmg" or "Hl" in b["classifications"]):
            return 1
        # If a.triggeredBy contains "Buff:" and b does not, b comes first
        elif "Buff:" in a["triggeredBy"] and "Buff:" not in b["triggeredBy"]:
            return 1
        # If b.triggeredBy contains "Buff:" and a does not, a comes first
        elif "Buff:" not in a["triggeredBy"] and "Buff:" in b["triggeredBy"]:
            return -1
        # Both have the same type or either both are "Dmg" types, or both have the same trigger condition
        # Retain their relative positions
        else:
            return 0

    allBuffs = sorted(allBuffs, key=cmp_to_key(compareBuffs))

    logger.info("ALL BUFFS:")
    # logger.info(allBuffs)
    # logger.info(weaponBuffsRange[0])

    # TODO change this to use databases instead
    for i in range(ROTATION_START, ROTATION_END + 1): # clear the content
        range = rotationSheet.getRange(f"D{i}:AH{i}")

        range.setValue("")
        range.setFontWeight("normal")
        range.clearNote()

        skillRange = rotationSheet.getRange(f"B{i}:C{i}")
        skillRange.setFontColor(None)
        skillRange.clearNote()

    # TODO change this to use databases instead
    statWarningRange = rotationSheet.getRange("I21")
    if CHECK_STATS:
        statWarningRange.setValue("The above values are accurate for the latest simulation!")
    else:
        statWarningRange.setValue("The above values are from a PREVIOUS SIMULATION.")

    currentTime = 0
    liveTime = 0

    # TODO change this to use databases instead
    for i in range(ROTATION_START, ROTATION_END + 1):
        swapped = False
        logger.info(f'new rotation line: {i}')
        healFound = False
        removeBuff = None
        removeBuffInstant = []
        passiveDamageQueue = []
        passiveDamageQueued = None
        activeCharacter = rotationSheet.getRange(f"A{i}").getValue() # TODO change this to use databases instead
        currentTime = rotationSheet.getRange(f"C{i}").getValue() # current time starts from the row below, at the end of this skill cast

        if lastCharacter is not None and activeCharacter != lastCharacter: # a swap was performed
            swapped = True
        # TODO change this to use databases instead
        currentSkill = rotationSheet.getRange(f"B{i}").getValue(); # the current skill
        # logger.info(f'lastSeen for {activeCharacter}: {lastSeen[activeCharacter]}. time diff: {currentTime - lastSeen[activeCharacter]} swapped: {swapped}');
        skillRef = getSkillReference(skillData, currentSkill, activeCharacter)
        if swapped and (currentTime - lastSeen[activeCharacter]) < 1 and not (skillRef["name"].startswith("Intro") or skillRef["name"].startswith("Outro")): # add swap-in time
            logger.info(f'adding extra time. current time: {currentTime}; lastSeen: {lastSeen[activeCharacter]}; skill: {skillRef["name"]}; time to add: {1 - (currentTime - lastSeen[activeCharacter])}')
            rotationSheet.getRange(dataCellTime + i).setValue(1 - (currentTime - lastSeen[activeCharacter]))
        if len(currentSkill) == 0:
            break
        lastSeen[activeCharacter] = rotationSheet.getRange(f"C{i}").getValue() + skillRef["castTime"] - skillRef["freezeTime"]
        classification = skillRef["classifications"]
        if "Temporal Bender" in skillRef["name"]:
            jinhsiOutroActive = True; # just for the sake of saving some runtime so we don't have to loop through buffs or passive effects...

        if skillRef["cooldown"] > 0:
            skillName = skillRef["name"].split(" (")[0]
            maxCharges = skillRef.get("maxCharges", 1)
            if not skillName in cooldownMap:
                cooldownMap[skillName] = {
                    "nextValidTime": currentTime,
                    "charges": maxCharges,
                    "lastUsedTime": currentTime
                }
            skillTrack = cooldownMap.get(skillName)
            elapsed = currentTime - skillTrack["lastUsedTime"]
            restoredCharges = min(
                elapsed // skillRef["cooldown"],
                maxCharges - skillTrack["charges"]
            )
            skillTrack["charges"] += restoredCharges
            if restoredCharges > 0:
                skillTrack["lastUsedTime"] += restoredCharges * skillRef["cooldown"]
            skillTrack["nextValidTime"] = skillTrack["lastUsedTime"] + skillRef["cooldown"]
            logger.info(f'{skillName}: {skillTrack["charges"]}, last used: {skillTrack["lastUsedTime"]}; restored: {restoredCharges}; next valid: {skillTrack["nextValidTime"]}')

            if skillTrack["charges"] > 0:
                if skillTrack["charges"] == maxCharges: # only update the timer when you're at max stacks to start regenerating the charge
                    skillTrack["lastUsedTime"] = currentTime
                skillTrack["charges"] -= 1
                cooldownMap[skillName] = skillTrack
            else:
                nextValidTime = skillTrack["nextValidTime"]
                logger.info(f'not enough charges for skill. next valid time: {nextValidTime}')
                # Handle the case where the skill is on cooldown and there are no available charges
                if nextValidTime - currentTime <= 1:
                    # If the skill will be available soon (within 1 second), adjust the rotation timing to account for this delay
                    delay = nextValidTime - currentTime
                    # TODO change this to use databases instead
                    rotationSheet.getRange(dataCellTime + i).setValue(max(rotationSheet.getRange(dataCellTime + i).getValue(), delay))
                    rotationSheet.getRange(f"C{i}").setFontColor("#FF7F50")
                    rotationSheet.getRange(f"C{i}").setNote(f"This skill is on cooldown until {nextValidTime:.2f}. A waiting time of {delay:.2f} seconds was added to accommodate.")
                else:
                    # If the skill will not be available soon, mark the rotation as illegal
                    # TODO change this to use databases instead
                    rotationSheet.getRange(f"C{i}").setFontColor("#ff0000")
                    rotationSheet.getRange(f"C{i}").setNote(f"Illegal rotation! This skill is on cooldown until {nextValidTime:.2f}")
                cooldownMap[skillName] = skillTrack

        # logger.info(f"Active Character: {activeCharacter}; Current buffs: {activeBuffs[activeCharacter]}; filtering for expired")

        activeBuffsArray = list(activeBuffs[activeCharacter])
        buffsToRemove = []
        buffEnergyItems = []
        #TODO move this function outside
        def filterActiveBuffs(activeBuff):
            endTime = (
                activeBuff["stackTime"] if activeBuff["buff"]["type"] == "StackingBuff" 
                else activeBuff["start_time"]
            ) + activeBuff["buff"]["duration"]
            # logger.info(f'{activeBuff["buff"]["name"]} end time: {endTime}; current time = {currentTime}')
            if activeBuff["buff"]["type"] == "BuffUntilSwap" and swapped:
                logger.info(f'BuffUntilSwap buff {activeBuff["name"]} was removed')
                return False
            if currentTime > endTime and activeBuff["buff"]["name"] == "Outro: Temporal Bender":
                global jinhsiOutroActive
                jinhsiOutroActive = False
            if currentTime > endTime and activeBuff["buff"]["type"] == "ResetBuff":
                logger.info(f'resetbuff has triggered: searching for {activeBuff["buff"]["classifications"]} to delete')
                buffsToRemove.append(activeBuff["buff"]["classifications"])
            return currentTime <= endTime  # Keep the buff if the current time is less than or equal to the end time

        activeBuffsArray = [buff for buff in activeBuffsArray if filterActiveBuffs(buff)]
        activeBuffs[activeCharacter] = set(activeBuffsArray)  # Convert the array back into a set

        for classification in buffsToRemove:
            activeBuffs[activeCharacter] = {
                buff for buff in activeBuffs[activeCharacter] if classification not in buff["buff"]["name"]
            }
            activeBuffs['Team'] = {
                buff for buff in activeBuffs['Team'] if classification not in buff['buff']['name']
            }

        if swapped and len(queuedBuffsForNext) > 0: # add outro skills after the buffuntilswap check is performed
            for queuedBuff in queuedBuffsForNext:
                found = False
                outroCopy = deepcopy(queuedBuff)
                outroCopy["buff"]["appliesTo"] = activeCharacter if outroCopy["buff"]["appliesTo"] == "Next" else outroCopy["buff"]["appliesTo"]
                activeSet = activeBuffs["Team"] if queuedBuff["buff"]["appliesTo"] == "Team" else activeBuffs[outroCopy["buff"]["appliesTo"]]

                for activeBuff in activeSet: # loop through and look for if the buff already exists
                    if activeBuff["buff"]["name"] == outroCopy["buff"]["name"] and activeBuff["buff"]["triggeredBy"] == outroCopy["buff"]["triggeredBy"]:
                        found = True
                        if activeBuff["buff"]["type"] == "StackingBuff":
                            effectiveInterval = activeBuff["buff"]["stackInterval"]
                            if activeBuff["buff"]["name"].startswith("Incandescence") and jinhsiOutroActive:
                                effectiveInterval = 1
                            logger.info(f'currentTime: {currentTime}; activeBuff.stackTime: {activeBuff["stackTime"]}; effectiveInterval: {effectiveInterval}')
                            if currentTime - activeBuff["stackTime"] >= effectiveInterval:
                                logger.info(f'updating stacks for {activeBuff["buff"]["name"]}: new stacks: {outroCopy["stacks"]} + {activeBuff["stacks"]}; limit: {activeBuff["buff"]["stackLimit"]}')
                                activeBuff["stacks"] = min(activeBuff["stacks"] + outroCopy["stacks"], activeBuff["buff"]["stackLimit"])
                                activeBuff["stackTime"] = currentTime
                        else:
                            activeBuff.startTime = currentTime
                            logger.info(f'updating startTime of {activeBuff["buff"]["name"]} to {currentTime}')
                if not found: # add a new buff
                    activeSet.append(outroCopy)
                    logger.info(f'adding new buff from queuedBuffForNext: {outroCopy["buff"]["name"]} x{outroCopy["stacks"]}')

                logger.info(f'Added queuedForNext buff [{queuedBuff["buff"]["name"]}] from {lastCharacter} to {activeCharacter}')
                logger.info(outroCopy)
            queuedBuffsForNext = []
        lastCharacter = activeCharacter
        if len(queuedBuffs) > 0: # add queued buffs procced from passive effects
            for queuedBuff in queuedBuffs:
                found = False
                copy = deepcopy(queuedBuff)
                copy["buff"]["appliesTo"] = activeCharacter if (copy["buff"]["appliesTo"] == "Next" or copy["buff"]["appliesTo"] == "Active") else copy["buff"]["appliesTo"]
                activeSet = activeBuffs['Team'] if copy["buff"]["appliesTo"] == "Team" else activeBuffs[copy["buff"]["appliesTo"]]

                logger.info(f'Processing queued buff [{queuedBuff["buff"]["name"]}]; applies to {copy["buff"]["appliesTo"]}')
                if queuedBuff["buff"]["type"] == "ConsumeBuff":
                    if removeBuff is not None:
                        logger.warning("UNEXPECTED double removebuff condition.")
                    removeBuff = copy["buff"]["classifications"] # remove this later, after other effects apply
                else:
                    for activeBuff in activeSet: # loop through and look for if the buff already exists
                        if activeBuff["buff"]["name"] == copy["buff"]["name"] and activeBuff["buff"]["triggeredBy"] == copy["buff"]["triggeredBy"]:
                            found = True
                            if activeBuff["buff"]["type"] == "StackingBuff":
                                effectiveInterval = activeBuff["buff"]["stackInterval"]
                                if activeBuff["buff"]["name"].startswith("Incandescence") and jinhsiOutroActive:
                                    effectiveInterval = 1
                                logger.info(f"currentTime: {currentTime}; activeBuff.stackTime: {activeBuff["stackTime"]}; effectiveInterval: {effectiveInterval}")
                                if currentTime - activeBuff["stackTime"] >= effectiveInterval:
                                    activeBuff["stackTime"] = copy["startTime"] # we already calculated the start time based on lastProc
                                    logger.info(f'updating stacks for {activeBuff["buff"]["name"]}: new stacks: {copy["stacks"]} + {activeBuff["stacks"]}; limit: {activeBuff["buff"]["stackLimit"]}; time: {activeBuff["stackTime"]}')
                                    activeBuff["stacks"] = min(activeBuff["stacks"] + copy["stacks"], activeBuff["buff"]["stackLimit"])
                                    activeBuff["stackTime"] = currentTime; # this actually is not accurate, will fix later. should move forward on multihits
                            else:
                                # sometimes a passive instance-triggered effect that procced earlier gets processed later. 
                                # to work around this, check which activated effect procced later
                                if copy["startTime"] > activeBuff["startTime"]:
                                    activeBuff["startTime"] = copy["startTime"]
                                    logger.info(f'updating startTime of {activeBuff["buff"]["name"]} to {copy["startTime"]}')
                    if not found: # add a new buff
                        # copy["startTime"] = currentTime
                        activeSet.append(copy)
                        logger.info(f'adding new buff from queue: {copy["buff"]["name"]} x{copy["stacks"]} at {copy["startTime"]}')
            queuedBuffs = []

        activeBuffsArrayTeam = list(activeBuffs['Team'])

        def filterTeamBuffs(activeBuff):
            endTime = (
                activeBuff["stack_time"] if activeBuff["buff"]["type"] == "StackingBuff" else activeBuff["start_time"]
            ) + activeBuff["buff"]["duration"]
            # logger.info(f'current teambuff end time: {endTime}; current time = {currentTime}')
            return currentTime <= endTime  # Keep the buff if the current time is less than or equal to the end time

        activeBuffsArrayTeam = [buff for buff in activeBuffsArrayTeam if filterTeamBuffs(buff)]
        activeBuffs["Team"] = set(activeBuffsArrayTeam)  # Convert the list back into a set

        # check for new buffs triggered at this time and add them to the active list
        for buff in allBuffs:
            # logger.info(buff)
            activeSet = activeBuffs["Team"] if buff["appliesTo"] == "Team" else activeBuffs[activeCharacter]
            triggeredBy = buff["triggeredBy"]
            if ";" in triggeredBy: # for cases that have additional conditions, remove them for the initial check
                triggeredBy = triggeredBy.split(";")[0]
            introOutro = "Outro" in buff["name"] or "Intro" in buff["name"]
            if len(triggeredBy) == 0 and introOutro:
                triggeredBy = buff["name"]
            if triggeredBy == "Any":
                triggeredBy = skillRef["name"] # well that's certainly one way to do it
            triggeredByConditions = triggeredBy.split(',')
            logger.info(f'checking conditions for {buff["name"]}; applies to: {buff["appliesTo"]}; conditions: {triggeredByConditions}; special: {buff["specialCondition"]}')
            isActivated = False
            specialActivated = False
            specialConditionValue = 0 # if there is a special >= condition, save this condition for potential proc counts later
            if buff["specialCondition"] and not "OnCast" in buff["specialCondition"] and (buff["canActivate"] == "Team" or buff["canActivate"] == activeCharacter): # special conditional
                if ">=" in buff["specialCondition"]:
                    # Extract the key and the value from the condition
                    
                    key, value = buff["specialCondition"].split(">=", 1)
                    # logger.info(f'checking condition {buff["specialCondition"]} for skill {skillRef["name"]}; {charData[activeCharacter]["dCond"].get(key)} >= {value}')

                    # Convert the value from string to number to compare
                    value = float(value)

                    # Check if the property (key) exists in skillRef
                    if key in charData[activeCharacter]["dCond"]:
                        # Evaluate the condition
                        isActivated = charData[activeCharacter]["dCond"][key] >= value
                        specialConditionValue = charData[activeCharacter][key]
                    else:
                        logger.info(f'condition not found: {buff["specialCondition"]} for skill {skillRef["name"]}')
                elif ":" in buff["specialCondition"]:
                    key, value = buff["specialCondition"].split(":", 1)
                    if "Buff" in key: # check the presence of a buff
                        isActivated = False
                        for activeBuff in activeSet: # loop through and look for if the buff already exists
                            if activeBuff["buff"]["name"] == value:
                                isActivated = True
                    else:
                        logger.info(f'unhandled colon condition: {buff["specialCondition"]} for skill {skillRef["name"]}')
                else:
                    logger.info(f'unhandled condition: {buff["specialCondition"]} for skill {skillRef["name"]}')
                specialActivated = isActivated
            else:
                specialActivated = True
            # check if any of the conditions in triggeredByConditions match
            isActivated = specialActivated
            for condition in triggeredByConditions:
                condition = condition.strip()
                conditionIsSkillName = len(condition > 2)
                extraCondition = True
                if buff["additionalCondition"]:
                    extraCondition = (
                        skillRef.classifications.includes(buff["additionalCondition"])
                        if len(buff["additionalCondition"]) == 2
                        else buff["additionalCondition"] in skillRef["name"])
                    logger.info(
                        f'checking for additional condition: {buff["additionalCondition"]}; '
                        f'length: {len(buff["additionalCondition"])}; '
                        f'skillRef class: {skillRef["classifications"]}; '
                        f'skillRef name: {skillRef["name"]}; fulfilled? {extraCondition}')
                # logger.info(f'checking condition {condition} for skill {skillRef["name"]}; buff.canActivate: {buff["canActivate"]}')
                if "Buff:" in condition: # check for the existence of a buff
                    buffName = condition.split(":")[1]
                    logger.info(f'checking for the existence of {buffName} at time {currentTime}')
                    buffArray = list(activeBuffs[activeCharacter])
                    buffArrayTeam = list(activeBuffs["Team"])
                    buffNames = [
                        f'{activeBuff["buff"]["name"]} x{activeBuff["stacks"]}'
                        if activeBuff["buff"]["type"] == "StackingBuff"
                        else activeBuff["buff"]["name"]
                        for activeBuff in buffArray] # Extract the name from each object
                    buffNamesTeam = [
                        f'{activeBuff["buff"]["name"]} x{activeBuff["stacks"]}'
                        if activeBuff["buff"]["type"] == "StackingBuff"
                        else activeBuff["buff"]["name"]
                        for activeBuff in buffArrayTeam] # Extract the name from each object
                    buffNamesString = ", ".join(buffNames)
                    buffNamesStringTeam = ", ".join(buffNamesTeam)
                    if (buffName in buffNamesString or buffName in buffNamesStringTeam) and extraCondition:
                        isActivated = specialActivated
                        break
                elif conditionIsSkillName:
                    for passiveDamageQueued in passiveDamageQueue:
                        logger.info(
                            f'buff: {buff["name"]}; passive damage queued: {passiveDamageQueued is not None}, condition: {condition}, '
                            f'name: {passiveDamageQueued["name"] if passiveDamageQueued is not None else "none"}, buff.canActivate: {buff["canActivate"]}, '
                            f'owner: {passiveDamageQueued["owner"] if passiveDamageQueued is not None else "none"}; additional condition: {buff["additionalCondition"]}')
                        if (passiveDamageQueued is not None
                            and (condition in passiveDamageQueued.name
                            or (condition == "Passive" and passiveDamageQueued.limit != 1 and extraCondition
                            and (passiveDamageQueued.type != "TickOverTime" and buff["canActivate"] != 'Active')))
                            and (buff["canActivate"] == passiveDamageQueued.owner or buff["canActivate"] in ["Team", "Active"])):
                            logger.info(f'[skill name] passive damage queued exists - adding new buff {buff["name"]}')
                            passiveDamageQueued.addBuff(createActiveStackingBuff(buff, currentTime, 1) if buff["type"] == "StackingBuff" else createActiveBuff(buff, currentTime))
                    # the condition is a skill name, check if it's included in the currentSkill
                    applicationCheck = extraCondition and buff["appliesTo"] == activeCharacter or buff["appliesTo"] == "Team" or buff["appliesTo"] == "Active" or introOutro or skillRef["source"] == activeCharacter
                    # logger.info(f'condition is skill name. application check: {["applicationCheck"]}, buff.canActivate: {buff["canActivate"]}, skillRef.source: {skillRef["source"]}')
                    if condition == "Swap" and not "Intro" in skillRef["name"] and (skillRef["castTime"] == 0 or '(Swap)' in skillRef["name"]): # this is a swap-out skill
                        if applicationCheck and ((buff["canActivate"] == activeCharacter or buff["canActivate"] == "Team") or (skillRef["source"] == activeCharacter and introOutro)):
                            isActivated = specialActivated
                            break
                    else:
                        if condition in currentSkill and applicationCheck and (buff["canActivate"] == activeCharacter or buff.canActivate == "Team" or (skillRef["source"] == activeCharacter and buff["appliesTo"] == "Next")):
                            isActivated = specialActivated
                            break
                else:
                    # logger.info(
                    #     f'passive damage queued: {passiveDamageQueued is not None}, condition: {condition}, '
                    #     f'name: {passiveDamageQueued.name if passiveDamageQueued is not None else "none"}, buff.canActivate: {buff["canActivate"]}, '
                    #     f'owner: {passiveDamageQueued.owner if passiveDamageQueued is not None else "none"}')
                    for passiveDamageQueued in passiveDamageQueue:
                        if passiveDamageQueued is not None and condition in passiveDamageQueued.classifications and (buff["canActivate"] == passiveDamageQueued.owner or buff["canActivate"] == "Team"):
                            logger.info(f'passive damage queued exists - adding new buff {buff["name"]}')
                            passiveDamageQueued.addBuff(createActiveStackingBuff(buff, currentTime, 1) if buff["type"] == "StackingBuff" else createActiveBuff(buff, currentTime))
                    # the condition is a classification code, check against the classification
                    logger.info(f'checking condition: {condition} healfound: {healFound}')
                    if (condition in classification or (condition == "Hl" and healFound)) and (buff["canActivate"] == activeCharacter or buff["canActivate"] == "Team") and extraCondition:
                        isActivated = specialActivated
                        break
            if buff["name"].startswith("Incandescence") and "Ec" in skillRef["classifications"]:
                isActivated = False
            if isActivated: # activate this effect
                found = False
                applyToCurrent = True
                stacksToAdd = 1
                logger.info(f'{buff["name"]} has been activated by {skillRef["name"]} at {currentTime}; type: {buff["type"]}; appliesTo: {buff["appliesTo"]}; class: {buff["classifications"]}')
                if "Hl" in buff["classifications"]: # when a heal effect is procced, raise a flag for subsequent proc conditions
                    healFound = True
                if buff["type"] == "ConsumeBuffInstant": # these buffs are immediately withdrawn before they are calculating
                    removeBuffInstant.append(buff["classifications"])
                elif buff.type == "ConsumeBuff":
                    if removeBuff is not None:
                        logger.info("UNEXPECTED double removebuff condition.")
                    removeBuff = buff["classifications"]; # remove this later, after other effects apply
                elif buff["type"] == "ResetBuff":
                    buffArray = list(activeBuffs[activeCharacter])
                    buffArrayTeam = list(activeBuffs["Team"])
                    buffNames = [
                        f'{activeBuff["buff"]["name"]} x{activeBuff["stacks"]}'
                        if activeBuff["buff"]["type"] == "StackingBuff"
                        else activeBuff["buff"]["name"]
                        for activeBuff in buffArray] # Extract the name from each object
                    buffNamesTeam = [
                        f'{activeBuff["buff"]["name"]} x{activeBuff["stacks"]}'
                        if activeBuff["buff"]["type"] == "StackingBuff"
                        else activeBuff["buff"]["name"]
                        for activeBuff in buffArrayTeam] # Extract the name from each object
                    buffNamesString = ", ".join(buffNames)
                    buffNamesStringTeam = ", ".join(buffNamesTeam)
                    if not buff["name"] in buffNamesString and not buff.name in buffNamesStringTeam:
                        logger.info("adding new active resetbuff")
                        activeSet.append(createActiveBuff(buff, currentTime))
                elif buff["type"] == "Dmg": # add a new passive damage instance
                    # queue the passive damage and snapshot the buffs later
                    logger.info(f'adding a new type of passive damage {buff["name"]}')
                    passiveDamageQueued = PassiveDamage(buff["name"], buff["classifications"], buff["buffType"], buff["amount"], buff["duration"], currentTime, buff["stackLimit"], buff["stackInterval"], buff["triggeredBy"], activeCharacter, i, buff["dCond"])
                    if buff["buffType"] == "TickOverTime":
                        # for DOT effects, procs are only applied at the end of the interval
                        passiveDamageQueued.lastProc = currentTime
                    passiveDamageQueue.append(passiveDamageQueued)
                    logger.info(passiveDamageQueued)
                elif buff["type"] == "StackingBuff":
                    effectiveInterval = buff["stackInterval"]
                    if "Incandescence" in buff["name"] and jinhsiOutroActive:
                        effectiveInterval = 1
                    logger.info(f'effectiveInterval: {effectiveInterval}; casttime: {skillRef["castTime"]}; hits: {skillRef["numberOfHits"]}; freezetime: {skillRef["freezeTime"]}')
                    if effectiveInterval < (skillRef["castTime"] - skillRef["freezeTime"]): # potentially add multiple stacks
                        if effectiveInterval == 0:
                            maxStacksByTime = skillRef["numberOfHits"]
                        else:
                            maxStacksByTime = (skillRef["castTime"] - skillRef["freezeTime"]) // effectiveInterval
                        stacksToAdd = min(maxStacksByTime, skillRef["numberOfHits"])
                    if buff["specialCondition"] and "OnCast" in buff["specialCondition"]:
                        stacksToAdd = 1
                    if buff.name == 'Resolution' and skillRef["name"].startswith("Intro: Tactical Strike"):
                        stacksToAdd = 15
                    if specialConditionValue > 0: # cap the stacks to add based on the special condition value
                        stacksToAdd = min(stacksToAdd, specialConditionValue)
                    # logger.info(f'this buff applies to: {buff["appliesTo"]}; active char: {activeCharacter}')
                    logger.info(f'{buff["name"]} is a stacking buff (special condition: {buff["specialCondition"]}). attempting to add {stacksToAdd} stacks')
                    for activeBuff in activeSet: # loop through and look for if the buff already exists
                        if activeBuff["buff"]["name"] == buff["name"] and activeBuff["buff"]["triggeredBy"] == buff["triggeredBy"]:
                            found = True
                            logger.info(f'current stacks: {activeBuff["stacks"]} last stack: {activeBuff["stackTime"]}; current time: {currentTime}')
                            if currentTime - activeBuff["stackTime"] >= effectiveInterval:
                                activeBuff["stacks"] = min(activeBuff["stacks"] + stacksToAdd, buff["stackLimit"])
                                activeBuff.stackTime = currentTime
                                logger.info("updating stacking buff: " + buff["name"])
                    if not found: # add a new stackable buff
                        activeSet.append(createActiveStackingBuff(buff, currentTime, min(stacksToAdd, buff["stackLimit"])))
                        # logger.info(f'adding new stacking buff: {buff["name"]}')
                else:
                    if "Outro" in buff["name"] or buff["appliesTo"] == "Next": # outro buffs are special and are saved for the next character
                        queuedBuffsForNext.append(createActiveBuff(buff, currentTime))
                        logger.info(f'queuing buff for next: {buff["name"]}')
                        applyToCurrent = False
                    else:
                        for activeBuff in activeSet: # loop through and look for if the buff already exists
                            if activeBuff["buff"]["name"] == buff["name"]:
                                # if (currentTime >= activeBuff.availableIn): # if the buff is available to refresh, then refresh. BROKEN. FIX THIS LATER. (only applies to jinhsi unison right now which really doesnt change anything if procs more)
                                activeBuff.startTime = currentTime + skillRef.castTime
                                # else:
                                #     logger.info(f'the buff {buff["name"]} is not available to refresh until {activeBuff["availableIn"]}; its interval is {activeBuff["stackInterval"]}')
                                found = True
                                logger.info(f'updating starttime of {buff["name"]} to {currentTime + skillRef["castTime"]}')
                        if not found:
                            if buff["type"] != "BuffEnergy": # buffenergy availablein is updated when it is applied later on
                                buff.availableIn = currentTime + buff.stackInterval
                            activeSet.append(createActiveBuff(buff, currentTime + skillRef.castTime))
                            # logger.info(f'adding new buff: {buff["name"]}')
                if buff["dCond"] is not None:
                    for value, condition in buff["dCond"].values():
                        evaluateDCond(value * stacksToAdd, condition)

        for removeBuff in removeBuffInstant:
            if removeBuff is not None:
                for activeBuff in activeBuffs[activeCharacter]:
                    if removeBuff in activeBuff["buff"]["name"]:
                        activeBuffs[activeCharacter].delete(activeBuff)
                        logger.info(f'removing buff instantly: {activeBuff["buff"]["name"]}')
                for activeBuff in activeBuffs["Team"]:
                    if removeBuff in activeBuff["buff"]["name"]:
                        activeBuffs["Team"].discard(activeBuff)
                        logger.info(f'removing buff instantly: {activeBuff["buff"]["name"]}')

        activeBuffsArray = list(activeBuffs[activeCharacter])
        buffNames = [
            f'{activeBuff["buff"]["name"]} x{activeBuff["stacks"]}'
            if activeBuff["buff"]["type"] == "StackingBuff"
            else activeBuff["buff"]["name"]
            for activeBuff in activeBuffsArray] # Extract the name from each object
        buffNamesString = ", ".join(buffNames)

        # logger.info(buffNamesString)
        # for buff in activeBuffs[activeCharacter]:
        #     logger.info(buff)

        # logger.info(f'Writing to: {dataCellCol + i}; {buffNamesString}')
        if len(activeBuffsArray) == 0: # TODO change this to use databases
            rotationSheet.getRange(dataCellCol + i).setValue("(0)")
        else:
            rotationSheet.getRange(dataCellCol + i).setValue(f'({len(activeBuffsArray)}) {buffNamesString}')
            
        activeBuffsArrayTeam = list(activeBuffs["Team"])
        buffNamesTeam = [
            f'{activeBuff["buff"]["name"]} x{activeBuff["stacks"]}'
            if activeBuff["buff"]["type"] == "StackingBuff"
            else activeBuff["buff"]["name"]
            for activeBuff in activeBuffsArrayTeam] # Extract the name from each object
        buffNamesStringTeam = ", ".join(buffNamesTeam)

        logger.info(f'buff names string team: {buffNamesStringTeam}')
        # for buff in activeBuffs["Team"]:
        #     logger.info(buff)

        # logger.info(f'Writing to: {dataCellColTeam + i}; ({len(activeBuffsArrayTeam)}) {buffNamesStringTeam}');
        # rotationSheet.getRange("A10").setValue(f'({len(activeBuffsArrayTeam)}) {buffNamesStringTeam}');
        if len(buffNamesStringTeam) == 0: # TODO change this to use databases instead
            rotationSheet.getRange(dataCellColTeam + i).setValue("(0)");
        else:
            rotationSheet.getRange(dataCellColTeam + i).setValue(f'({len(activeBuffsArrayTeam)}) {buffNamesStringTeam}')

        #TODO move this function outside
        """
        Updates the total buff map.
        @buffCategory - The base type of the buff (All , AllEle, Fu, Sp, etc)
        @buffType - The specific type of the buff (Bonus, Attack, Additive)
        @buffAmount - The amount of the buff to add
        @buffMax - The maximum buff value for the stack, for particular buffs have multiple different variations contributing to the same cap (e.g. Jinhsi Incandesence)
        """
        def updateTotalBuffMap(buffCategory, buffType, buffAmount, buffMax): # TODO remove the references to variables outside the function scope (totalBuffMap, charData, activeCharacter, skillRef)
            # logger.info(f'updating buff for {buffCategory}; type={buffType}; amount={buffAmount}; max={buffMax}')
            key = buffCategory
            if buffCategory == "All":
                for buff in STANDARD_BUFF_TYPES:
                    newKey = translateClassificationCode(buff)
                    newKey = f'{newKey} ({buffType})' if buffType == "Deepen" else f'{newKey}'
                    currentAmount = totalBuffMap[newKey]
                    if not newKey in totalBuffMap:
                        return
                    totalBuffMap.set(newKey, currentAmount + buffAmount) # Update the total amount
                    # logger.info(f'updating buff {newKey} to {currentAmount} (+{buffAmount})')
            elif buffCategory == "AllEle":
                for buff in ELEMENTAL_BUFF_TYPES:
                    newKey = translateClassificationCode(buff)
                    currentAmount = totalBuffMap[newKey]
                    if not newKey in totalBuffMap:
                        return
                    totalBuffMap[newKey] = currentAmount + buffAmount # Update the total amount
                    # logger.info(f'updating buff {newKey} to {currentAmount} (+{buffAmount})')
            else:
                categories = buffCategory.split(",")
                for category in categories:
                    newKey = translateClassificationCode(category)
                    baseKey = removeTextWithinParentheses(newKey)
                    newKey = f'{newKey} ({buffType})' if buffType == "Deepen" else f'{newKey}'
                    currentAmount = totalBuffMap[newKey]
                    if "*" in buffType: # this is a dynamic buff value that multiplies by a certain condition
                        split = buffType.split("*")
                        buffType = split[0]
                        buffAmount *= charData[activeCharacter]["dCond"][split[1]]
                        logger.info(f'found multiplicative condition for buff amount: multiplying {buffAmount} by {split[1]} ({charData[activeCharacter]["dCond"][split[1]]})')
                    buffKey = "Specific" if buffType == "Bonus" else ("Deepen" if buffType == "Deepen" else "Multiplier")
                    if buffType == "Additive": # an additive value to a skill multiplier
                        # todo
                        buffKey = "Additive"
                        newKey = f'{baseKey} ({buffKey})'
                        if newKey in totalBuffMap:
                            currentBonus = totalBuffMap[newKey]
                            maxValue = 99999
                            if buffMax > 0:
                                maxValue = buffMax
                            totalBuffMap[newKey] = min(maxValue, currentBonus + buffAmount) # Update the total amount
                            logger.info('updating {newKey}: {currentBonus} + {buffAmount}, capped at {maxValue}')
                        else: # add the skill key as a new value for potential procs
                            totalBuffMap[newKey] = buffAmount
                            logger.info(f'no match, but adding additive key {newKey} = {buffAmount}')
                    elif buffKey == "Deepen" and not baseKey in STANDARD_BUFF_TYPES: # apply element-specific deepen effects IF MATCH
                        if (len(category) == 2 and category in skillRef["classifications"]) or (len(category) > 2 and category in skillRef["name"]):
                            newKey = "Deepen"
                            currentAmount = totalBuffMap[newKey]
                            logger.info(f'updating amplify; current {currentAmount} (+{buffAmount})')
                            totalBuffMap[newKey] = currentAmount + buffAmount # Update the total amount
                    elif buffType == "Resistance": # apply resistance effects IF MATCH
                        if (len(category) == 2 and category in skillRef["classifications"]) or (len(category) > 2 and category in skillRef["name"]):
                            newKey = "Resistance"
                            currentAmount = totalBuffMap[newKey]
                            logger.info(f'updating res shred; current {currentAmount} (+{buffAmount})')
                            totalBuffMap[newKey] = currentAmount + buffAmount # Update the total amount
                    elif buffType == "Ignore Defense": # ignore defense IF MATCH
                        if (len(category) == 2 and category in skillRef["classifications"]) or (len(category) > 2 and category in skillRef["name"]):
                            newKey = "Ignore Defense"
                            currentAmount = totalBuffMap[newKey]
                            logger.info(f'updating ignore def; current {currentAmount} (+{buffAmount})')
                            totalBuffMap[newKey] = currentAmount + buffAmount # Update the total amount
                    else:
                        if not newKey in totalBuffMap: # skill-specific buff
                            if newKey in skillRef["name"]:
                                currentBonus = totalBuffMap[buffKey]
                                totalBuffMap[buffKey] = currentBonus + buffAmount # Update the total amount
                                logger.info(f'updating new key from {newKey}; current bonus: {currentBonus}; buffKey: {buffKey}; buffAmount: {buffAmount}')
                            else: # add the skill key as a new value for potential procs
                                totalBuffMap[f'{newKey} ({buffKey})'] = buffAmount
                                logger.info(f'no match, but adding key {newKey} ({buffKey})')
                        else:
                            totalBuffMap.set(newKey, currentAmount + buffAmount); # Update the total amount
                    # logger.info(f'updating buff {key} to {currentAmount} (+{buffAmount})')

        #TODO move this function outside
        # Process buff array
        def processBuffs(buffs):
            for buffWrapper in buffs:
                buff = buffWrapper["buff"]
                logger.info(f'buff: {buff["name"]}; buffType: {buff["type"]}; current time: {currentTime}; available In: {buff["availableIn"]}')
                if buff["name"] == "Rythmic Vibrato": # we don't re-poll buffs for passive damage instances currently so it needs to keep track of this lol
                    rythmicVibrato = buffWrapper["stacks"]

                if buff["type"] == "BuffEnergy" and currentTime >= buff["availableIn"]: # add energy instead of adding the buff
                    logger.info(f'adding BuffEnergy dynamic condition: " + {buff["amount"]} + " for type " + {buff["buffType"]}')
                    buff.availableIn = currentTime + buff["stackInterval"]
                    charData[activeCharacter]["dCond"][buff["buffType"]] = float(charData[activeCharacter]["dCond"][buff["buffType"]]) + float(buff["amount"]) * max(float(buffWrapper["stacks"]), 1)
                    logger.info(f'total {buff["buffType"]} after: {charData[activeCharacter]["dCond"][buff["buffType"]]}')

                # special buff types are handled slightly differently
                specialBuffTypes = ["Attack", "Health", "Defense", "Crit", "Crit Dmg"]
                if buff["buffType"] in specialBuffTypes:
                    updateTotalBuffMap(buff["buffType"], "", buff["amount"] * (buffWrapper["stacks"] if buff["type"] == "StackingBuff" else 1), buff["amount"] * buff["stackLimit"])
                else: # for other buffs, just use classifications as is
                    updateTotalBuffMap(buff["classifications"], buff["buffType"], buff["amount"] * (buffWrapper["stacks"] if buff["type"] == "StackingBuff" else 1), buff["amount"] * buff["stackLimit"])

        #TODO move this function outside
        def writeBuffsToSheet(i): # TODO change this to use databases instead
            sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Calculator')
            
            bufferRange = f"I{i}:AG{i}"
            values = []
            
            for key in totalBuffMap.keys():
                value = totalBuffMap[key]
                match(key):
                    case "Attack":
                        value += bonusStats[activeCharacter]["attack"]
                    case "Health":
                        value += bonusStats[activeCharacter]["health"]
                    case "Defense":
                        value += bonusStats[activeCharacter]["defense"]
                    case "Crit":
                        value += charData[activeCharacter]["crit"]
                    case "Crit Dmg":
                        value += charData[activeCharacter]["critDmg"]
                values.append(value)
                # logger.info(f'{key} value : {value}')

            if len(values) > 25:
                values = values[:25]
            bufferRange.setValues([values]) # TODO change this to use databases instead

        totalBuffMap = {
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
        }
        teamBuffMap = totalBuffMap.copy()

        if weaponData[activeCharacter]["mainStat"] in totalBuffMap:
            currentAmount = totalBuffMap[weaponData[activeCharacter]["mainStat"]]
            totalBuffMap[weaponData[activeCharacter]["mainStat"]] = currentAmount + weaponData[activeCharacter]["mainStatAmount"]
            logger.info(f'adding mainstat {weaponData[activeCharacter]["mainStat"]} (+{weaponData[activeCharacter]["mainStatAmount"]}) to {activeCharacter}')
        logger.info("BONUS STATS:")
        logger.info(charData[activeCharacter]["bonusStats"])
        for statPair in charData[activeCharacter]["bonusStats"]:
            stat = statPair[0]
            value = statPair[1]
            currentAmount = totalBuffMap.get(stat, 0)
            totalBuffMap[stat] = currentAmount + value
        processBuffs(activeBuffsArray)

        processBuffs(activeBuffsArrayTeam)
        lastTotalBuffMap[activeCharacter] = totalBuffMap
        for passiveDamageQueued in passiveDamageQueue:
            if passiveDamageQueued is not None: # snapshot passive damage BEFORE team buffs are applied
                # TEMP: move this above activeBuffsArrayTeam and implement separate buff tracking
                for instance in passiveDamageInstances: # remove any duplicates first
                    if instance.name == passiveDamageQueued.name:
                        instance.remove = True
                        logger.info(f'new instance of passive damage {passiveDamageQueued.name} found. removing old entry')
                        break
                passiveDamageQueued.setTotalBuffMap(totalBuffMap)
                passiveDamageInstances.append(passiveDamageQueued)

        writeBuffsToSheet(i)
        if "Buff" in skillRef["type"]:
            rotationSheet.getRange(dataCellColDmg + i).setValue(0) # TODO change this to use databases instead
            continue
        
        # damage calculations
        # logger.info(charData[activeCharacter])
        # logger.info("bonus input stats:")
        # logger.info(bonusStats[activeCharacter])
        logger.info(f'DAMAGE CALC for : {skillRef["name"]}')
        logger.info(skillRef)
        logger.info(f'multiplier: {totalBuffMap["Multiplier"]}')
        passive_damage_instances = [passiveDamage for passiveDamage in passiveDamageInstances if not passiveDamage.canRemove(currentTime, removeBuff)]
        # TODO extract this function
        def evaluateDCond(condition, value):
            if value and value != 0:
                # logger.info(f'evaluating dynamic condition for {skillRef["name"]}: {condition} x{value}')
                if value < 0:
                    cellInfo = rotationSheet.getRange('B' + i)
                    if activeCharacter == "Jinhsi" and condition == "Concerto" and "Unison" in buffNames:
                        cellInfo.setNote("The Unison condition has covered the Conerto cost for this Outro.") # TODO change this to use databases instead
                    else:
                        if charData[activeCharacter]["dCond"][condition] + value < 0: # ILLEGAL INPUT
                            cellInfo.setFontColor('#ff0000') # TODO change this to use databases instead
                            if condition == "Resonance":
                                # Determine main stat amount if it is "Energy Regen"
                                mainStatAmount = (
                                    weaponData[activeCharacter]["mainStatAmount"] if weaponData[activeCharacter]["mainStat"] == "Energy Regen" else 0
                                )
                                # Get the energy recharge from bonus stats
                                bonusEnergyRecharge = bonusStats[activeCharacter]["energyRecharge"]
                                # Find the additional energy recharge from character data's bonus stats
                                additionalEnergyRecharge = next(
                                    (amount for stat, amount in charData[activeCharacter]["bonusStats"] if stat == "Energy Regen"), 0
                                )
                                # Calculate the total energy recharge
                                energyRecharge = mainStatAmount + bonusEnergyRecharge + additionalEnergyRecharge
                                baseEnergy = charData[activeCharacter]["dCond"][condition] / (1 + energyRecharge)
                                requiredRecharge = ((value * -1) / baseEnergy - energyRecharge - 1) * 100
                                # TODO change this to use databases instead
                                cellInfo.setNote(f'Illegal rotation! At this point, you have {charData[activeCharacter]["dCond"][condition]:.2f} out of the required {(value * -1)} {condition} (Requires an additional {requiredRecharge:.1f}% ERR)')
                            else:
                                noMessage = False
                                if activeCharacter == "Jiyan" and "Windqueller" in skillRef["name"]:
                                    noMessage = True
                                if not noMessage:
                                    # TODO change this to use databases instead
                                    cellInfo.setNote(f'Illegal rotation! At this point, you have {charData[activeCharacter]["dCond"][condition]:.2f} out of the required {(value * -1)} {condition}')
                            initialDCond[activeCharacter][condition] = (value * -1) - charData[activeCharacter]["dCond"][condition]
                        else:
                            # TODO change this to use databases instead
                            cellInfo.setNote(f'At this point, you have generated {charData[activeCharacter]["dCond"][condition]:.2f} out of the required {(value * -1)} {condition}')
                        if activeCharacter == "Danjin" or skillRef["name"].startswith("Outro") or skillRef["name"].startswith("Liberation"):
                            charData[activeCharacter]["dCond"][condition] = 0; # consume all
                        else:
                            if activeCharacter == "Jiyan" and "Qingloong Mode" in buffNames and "Windqueller" in skillRef["name"]: # increase skill damage bonus for this action if forte was consumed, but only if ult is NOT active
                                currentAmount = totalBuffMap["Specific"]
                                totalBuffMap["Specific"] += 0.2
                            else: # adjust the dynamic condition as expected
                                charData[activeCharacter]["dCond"][condition] = max(0, charData[activeCharacter]["dCond"][condition] + value)
                else:
                    if not charData[activeCharacter]["dCond"][condition]:
                        logger.warning("EH? NaN condition " + condition + " for character " + activeCharacter)
                        charData[activeCharacter].dCond.set(condition, 0)
                    if condition == "Resonance":
                        handleEnergyShare(value, activeCharacter)
                    else:
                        if condition == "Forte":
                            logger.info(f'maximum forte: {CHAR_CONSTANTS[activeCharacter]["maxForte"]}; current: {min(charData[activeCharacter]["dCond"][condition])}; value to add: {value}')
                            charData[activeCharacter]["dCond"][condition] = min(charData[activeCharacter]["dCond"][condition] + value, CHAR_CONSTANTS[activeCharacter].maxForte)
                        else:
                            charData[activeCharacter]["dCond"][condition] = charData[activeCharacter]["dCond"][condition] + value
                logger.info(charData[activeCharacter])
                logger.info(charData[activeCharacter]["dCond"])
                logger.info(f'dynamic condition [{condition}] updated: {charData[activeCharacter]["dCond"][condition]} (+{value})')
        for value, condition in skillRef["dCond"].items():
            evaluateDCond(value, condition)
        if skillRef.damage > 0:
            for passiveDamage in passiveDamageInstances:
                logger.info(f'checking proc conditions for {passiveDamage.name}; {passiveDamage.canProc(currentTime, skillRef)} ({skillRef["name"]})')
                if passiveDamage.canProc(currentTime, skillRef) and passiveDamage.checkProcConditions(skillRef):
                    passiveDamage.updateTotalBuffMap()
                    procs = passiveDamage.handleProcs(currentTime, skillRef.castTime - skillRef.freezeTime, skillRef.numberOfHits)
                    damageProc = passiveDamage.calculateProc(activeCharacter) * procs
                    # TODO change this to use databases instead
                    cell = rotationSheet.getRange(dataCellColDmg + passiveDamage.slot)
                    currentDamage = cell.getValue()
                    cell.setValue(currentDamage + damageProc)

                    # TODO change this to use databases instead
                    cellInfo = rotationSheet.getRange("H" + passiveDamage.slot)
                    cellInfo.setFontWeight("bold")
                    cellInfo.setNote(passiveDamage.getNote())
        # TODO change this to use databases instead
        rotationSheet.getRange("D" + i).setValue(charData[activeCharacter].dCond.get("Resonance").toFixed(2))
        rotationSheet.getRange("E" + i).setValue(charData[activeCharacter].dCond.get("Concerto").toFixed(2))

        additiveValueKey = f'{skillRef["name"]} (Additive)'
        damage = skillRef["damage"] * (1 if "Ec" in skillRef["classifications"] else skillLevelMultiplier) + totalBuffMap.get(additiveValueKey, 0)
        attack = (charData[activeCharacter]["attack"] + weaponData[activeCharacter]["attack"]) * (1 + totalBuffMap["Attack"] + bonusStats[activeCharacter]["attack"]) + totalBuffMap["Flat Attack"]
        health = charData[activeCharacter]["health"] * (1 + totalBuffMap["Health"] + bonusStats[activeCharacter]["health"]) + totalBuffMap["Flat Health"]
        defense = charData[activeCharacter]["defense"] * (1 + totalBuffMap["Defense"] + bonusStats[activeCharacter]["defense"]) + totalBuffMap["Flat Defense"]
        critMultiplier = (1 - min(1,(charData[activeCharacter]["crit"] + totalBuffMap["Crit"]))) * 1 + min(1,(charData[activeCharacter]["crit"] + totalBuffMap["Crit"])) * (charData[activeCharacter]["critDmg"] + totalBuffMap["Crit Dmg"])
        damageMultiplier = getDamageMultiplier(skillRef["classifications"], totalBuffMap)
        # logger.info(f'char defense: {charData[activeCharacter]["defense"]} weapon def: {weaponData[activeCharacter]["defense"]}; buff def: {totalBuffMap["Defense"]} bonus stat def: {bonusStats[activeCharacter]["defense"]}; flat def: {totalBuffMap["Flat Defense"]}')
        scaleFactor = defense if "Df" in skillRef["classifications"] else (health if "Hp" in skillRef["classifications"] else attack)
        totalDamage = damage * scaleFactor * critMultiplier * damageMultiplier * (0 if weaponData[activeCharacter]["weapon"]["name"] == "Nullify Damage" else 1)
        # logger.info(charData[activeCharacter])
        # logger.info(weaponData[activeCharacter])
        logger.info(f'skill damage: {damage:.2f}; attack: {(charData[activeCharacter]["attack"] + weaponData[activeCharacter]["attack"]):.2f} x {(1 + totalBuffMap["Attack"] + bonusStats[activeCharacter]["attack"]):.2f} + {totalBuffMap["Flat Attack"]}; crit mult: {critMultiplier:.2f}; dmg mult: {damageMultiplier:.2f}; defense: {defense}; total dmg: {totalDamage:.2f}')
        # TODO change this to use databases instead
        rotationSheet.getRange(dataCellColDmg + i).setValue(rotationSheet.getRange(dataCellColDmg + i).getValue() + totalDamage)

        updateDamage(skillRef["name"], skillRef["classifications"], activeCharacter, damage, totalDamage, totalBuffMap)
        if mode == "Opener" and character1 == activeCharacter and skillRef["name"].startswith("Outro"):
            mode = "Loop"
            openerTime = rotationSheet.getRange(f'C{i}').getValue() # TODO change this to use databases instead
        liveTime += skillRef["castTime"] # live time

        if removeBuff is not None:
            for activeBuff in activeBuffs[activeCharacter]:
                if removeBuff in activeBuff["buff"]["name"]:
                    activeBuffs[activeCharacter].discard(activeBuff)
                    logger.info(f'removing buff: {activeBuff["buff"]["name"]}')
            for activeBuff in activeBuffs["Team"]:
                if removeBuff in activeBuff["buff"]["name"]:
                    activeBuffs["Team"].discard(activeBuff)
                    logger.info(f'removing buff: {activeBuff["buff"]["name"]}')

    # TODO change this to use databases instead
    startRow = dataCellRowNextSub # Starting at 66
    startColIndex = SpreadsheetApp.getActiveSpreadsheet().getRange(dataCellColNextSub + "1").getColumn() # Get the column index for 'I' which is 9

    # logger.info(charStatGains[characters[0]]);
    # logger.info(charEntries[characters[0]]);

    # TODO change this to use databases instead
    finalTime = rotationSheet.getRange(f'C{ROTATION_END}').getValue()
    finalDamage = rotationSheet.getRange("G32").getValue()
    logger.info(f'real time: {liveTime}; final in-game time: {rotationSheet.getRange('C{ROTATION_END}').getValue()}')
    rotationSheet.getRange("H27").setNote(f'Total Damage: {openerDamage:.2f} in {openerTime:.2f}s')
    rotationSheet.getRange("H28").setNote(f'Total Damage: {loopDamage:.2f} in {(finalTime - openerTime):.2f}s')
    rotationSheet.getRange("H27").setValue(openerDamage / openerTime if openerTime > 0 else 0)
    rotationSheet.getRange("H28").setValue(loopDamage / (finalTime - openerTime))

    wDpsLoopTime = 120 - openerTime
    wDpsLoops = wDpsLoopTime / (finalTime - openerTime)
    wDps = (openerDamage + loopDamage * wDpsLoops) / 120

    rotationSheet.getRange("H29").setValue(f'{wDps:.2f}') # TODO change this to use databases instead
    if CHECK_STATS:
        for character in characters:
            if charEntries[character] > 0: # Using [character] to get each character's entry
                stats = charStatGains[character]
                colOffset = 0 # Initialize column offset for each character

                for key in stats.keys():
                    if damageByCharacter[character] == 0:
                        stats[key] = 0
                    else:
                        stats[key] /= damageByCharacter[character] # charEntries[character]
                    # Calculate the range using row and column indices and write data horizontally.
                    # TODO change this to use databases instead
                    cell = rotationSheet.getRange(startRow, startColIndex + colOffset)
                    cell.setValue(stats[key])
                    colOffset += 1 # Move to the next column for the next stat
                logger.info(charStatGains[character])
                startRow += 1 # Move to the next row after writing all stats for a character

    resultIndex = dataCellRowResults
    logger.info(totalDamageMap)
    for key, value in totalDamageMap.items():
        # TODO change this to use databases instead
        cell = rotationSheet.getRange(dataCellColResults + resultIndex)
        cell.set_value(value)
        resultIndex += 1

    # write initial and final dconds

    # TODO change this to use databases instead
    startRow = dataCellRowDCond # Starting at 66
    startColIndex = SpreadsheetApp.getActiveSpreadsheet().getRange(dataCellColDCond + "1").getColumn()
    for character in characters:
        colOffset = 0 # Initialize column offset for each character
        # TODO change this to use databases instead
        rotationSheet.getRange(startRow, startColIndex + colOffset).setValue(initialDCond[character]["Forte"])
        rotationSheet.getRange(startRow, startColIndex + (colOffset + 1)).setValue(initialDCond[character]["Resonance"])
        rotationSheet.getRange(startRow, startColIndex + (colOffset + 2)).setValue(initialDCond[character]["Concerto"])
        rotationSheet.getRange(startRow, startColIndex + colOffset + 3).setValue(charData[character]["dCond"]["Forte"])
        rotationSheet.getRange(startRow, startColIndex + (colOffset + 4)).setValue(charData[character]["dCond"]["Resonance"])
        rotationSheet.getRange(startRow, startColIndex + (colOffset + 5)).setValue(charData[character]["dCond"]["Concerto"])
        startRow += 1

    exportBuild()

    # Output the tracked buffs for each time point (optional)
    for entry in trackedBuffs:
        logger.info(f'Time: {entry["time"]}, Active Buffs: {", ".join(entry["activeBuffs"])}')

def importBuild():
    # TODO change this to use databases instead
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Calculator")
    errorRange = "I25"
    buildRange = "K24"
    confirmRange = "N24"
    build = rotationSheet.getRange(buildRange).getValue()
    confirm = rotationSheet.getRange(confirmRange).getValue()
    rotationSheet.getRange(errorRange).setValue("")

    if not confirm:
        if build and build.length > 0:
            # TODO change this to use databases instead
            rotationSheet.getRange(errorRange).setValue("A build to import was found, but the confirmation checkbox was not set.")
            logger.info("A build to import was found, but the confirmation checkbox was not set.")
    elif build and len(build) > 0:

        # TODO change this to use databases instead
        range = rotationSheet.getRange(f'A{ROTATION_START}:B{ROTATION_END}')

        # TODO change this to use databases instead
        range.setValue("")
        range.setFontWeight("normal")
        range.clearNote()
        sections = build.split(";")
        if len(sections) != 5: # TODO change this to use databases instead
            rotationSheet.getRange(errorRange).setValue(f'Malformed build. Could not import. Found {len(sections)} sections; expected 5')
        else:
            rotaSection = sections[4]
            charSections = ""
            divider = ""
            for i in range(1, 4): # import the 3 character sections
                charSections += divider
                charSections += sections[i]
                divider = ";"
            # for i in range(1, 3):
                # logger.info(sections[i + 1])
                # rotationSheet.getRange(f'B{7 + i}').setValue(sections[i + 1].split(",")[0])
            # time.sleep(2)

            # import the base character details
            rowMappings = [ # TODO change this to use databases instead
                {cellRange: "B7:Z7", percentRange: "L7:Z7", extraRange: "I11:L11"},
                {cellRange: "B8:Z8", percentRange: "L8:Z8", extraRange: "I12:L12"},
                {cellRange: "B9:Z9", percentRange: "L9:Z9", extraRange: "I13:L13"}
            ]

            rows = charSections.split(";"); # Split by each character input block

            for rowIndex in range(min(len(rowMappings), len(rows))):
                values = rows[rowIndex].split(",")

                if len(values) < 29:
                    logger.warning(f'Row {rowIndex + 1} does not contain the required 29 values.')
                    continue; # Skip this row if it doesn't have enough values

                # TODO change this to use databases instead
                cellRange = rowMappings[rowIndex].cellRange
                percentRange = rowMappings[rowIndex].percentRange
                extraRange = rowMappings[rowIndex].extraRange

                # TODO change this to use databases instead
                weaponRange = "D7:D9"
                weaponRangeRules = sheet.getRange(weaponRange).getDataValidations()
                sheet.getRange(weaponRange).clearDataValidations()

                try: # TODO change this to use databases instead
                    # Get the first 25 values for cells Bx to Zx
                    mainValues = values[:25]
                    # Get the last 4 values for cells Ix to Lx
                    extraValues = values[25:29]

                    # Convert 1D arrays to 2D arrays for setValues
                    mainValues2D = [mainValues]
                    extraValues2D = [extraValues]

                    # Set values in one batch operation for the main cells
                    sheet.getRange(cellRange).setValues(mainValues2D)

                    # Set values in one batch operation for the extra cells
                    sheet.getRange(extraRange).setValues(extraValues2D)

                    # Format specific columns as percentages (L to Z) for main values
                    sheet.getRange(percentRange).setNumberFormat('0.00%')

                    # Format extra columns (I to L) as percentages
                    sheet.getRange(extraRange).setNumberFormat('0.00%')
                except Exception as e:
                    logger.error(f'error in importing build: {e}')
                finally: # TODO change this to use databases instead
                    sheet.getRange(weaponRange).setDataValidations(weaponRangeRules)

            # import the rotation

            startingRow = 34 # TODO change this to use databases instead

            entries = rotaSection.split(",")

            # Prepare arrays to hold character names and skills separately
            characterData = []
            skillData = []

            for entry in entries:
                character, skill = entry.split("&")
                characterData.append([character])
                skillData.append([skill])

            # Get ranges for characters and skills
            # TODO change this to use databases instead
            characterRange = sheet.getRange(f'A{startingRow}:A{startingRow + len(characterData) - 1}')
            skillRange = sheet.getRange(f'B{startingRow}:B{startingRow + len(skillData) - 1}')

            # skillValidationRules = skillRange.getDataValidations()
            # skillRange.clearDataValidations()

            try:
                # Batch update characters (column A)
                characterRange.setValues(characterData)

                # Wait briefly to allow drop-downs to refresh
                # time.sleep(3)

                # Batch update skills (column B)
                skillRange.setValues(skillData);
                rotationSheet.getRange(confirmRange).setValue(False) # TODO change this to use databases instead
            except Exception as e:
                logger.error(f'error in importing build: {e}')
            # finally:
                # rebuildRotationValidation()

# TODO change this to use databases instead
def rebuildRotationValidation():
    spreadsheet = SpreadsheetApp.getActiveSpreadsheet()
    sheet = spreadsheet.getSheetByName("Calculator")

    # Define the range on the "Calculator" sheet
    range = sheet.getRange("B34:B145")

    # Define the source range for the dropdown options on the "RotaSkills" sheet
    sourceSheet = spreadsheet.getSheetByName("RotaSkills")
    sourceRange = sourceSheet.getRange(f'A1:AA1')

    # Create the data validation rule for a dropdown based on the source range
    rule = SpreadsheetApp.newDataValidation().requireValueInRange(sourceRange, True).setAllowInvalid(False).build()
    # true indicates auto-advanced validation
    # setAllowInvalid is Optional: do not allow invalid entries

    # Apply the validation rule to the target range
    range.setDataValidation(rule)

def updateDamage(name, classifications, activeCharacter, damage, totalDamage, totalBuffMap):
    updateDamage(name, classifications, activeCharacter, damage, totalDamage, totalBuffMap, 0)

# Updates the damage values in the substat estimator as well as the total damage distribution.
# Has an additional 'damageMultExtra' field for any additional multipliers added on by... hardcoding.
def updateDamage(name, classifications, activeCharacter, damage, totalDamage, totalBuffMap, damageMultExtra):
    charEntries[activeCharacter] += 1
    damageByCharacter[activeCharacter] += totalDamage
    if mode == "Opener":
        global openerDamage
        openerDamage += totalDamage
    else:
        global loopDamage
        loopDamage += totalDamage
    if CHECK_STATS:
        for stat, value in statCheckMap.items():
            if totalDamage > 0:
                # logger.info(f'current stat:{stat} ({value}). attack: " + {charData[activeCharacter]["attack"] + weaponData[activeCharacter]["attack"] * (1 + totalBuffMap["Attack"] + bonusStats[activeCharacter]["attack"]) + totalBuffMap["Flat Attack"]}')
                currentAmount = totalBuffMap[stat]
                totalBuffMap[stat] = currentAmount + value
                attack = (charData[activeCharacter]["attack"] + weaponData[activeCharacter]["attack"]) * (1 + totalBuffMap["Attack"] + bonusStats[activeCharacter]["attack"]) + totalBuffMap["Flat Attack"]
                # logger.info(f'new attack: {attack}')
                health = (charData[activeCharacter]["health"]) * (1 + totalBuffMap["Health"] + bonusStats[activeCharacter]["health"]) + totalBuffMap["Flat Health"]
                defense = (charData[activeCharacter]["defense"]) * (1 + totalBuffMap['Defense'] + bonusStats[activeCharacter]["defense"]) + totalBuffMap["Flat Defense"]
                critMultiplier = (1 - min(1, (charData[activeCharacter]["crit"] + totalBuffMap["Crit"]))) * 1 + min(1, (charData[activeCharacter]["crit"] + totalBuffMap["Crit"])) * (charData[activeCharacter]["critDmg"] + totalBuffMap["Crit Dmg"])
                damageMultiplier = getDamageMultiplier(classifications, totalBuffMap) + (damageMultExtra or 0)
                scaleFactor = defense if "Df" in classifications else (health if "Hp" in classifications else attack)
                newTotalDamage = damage * scaleFactor * critMultiplier * damageMultiplier * (0 if weaponData[activeCharacter]["weapon"]["name"] == "Nullify Damage" else 1)
                # logger.info(f'damage: {damage}; scaleFactor: {scaleFactor}; critMult: {critMultiplier}; damageMult: {damageMultiplier}; weaponMult: {(0 if weaponData[activeCharacter]["weapon"]["name"] == "Nullify Damage" else 1)}')
                # logger.info(f'new total dmg from stat: {stat}: {newTotalDamage} vs old: {totalDamage}; gain = {newTotalDamage / totalDamage - 1}; weapon: {weaponData[activeCharacter]["weapon"]["name"]}')
                charStatGains[activeCharacter][stat] += newTotalDamage - totalDamage
                totalBuffMap[stat] = currentAmount # unset the value after

    # update damage distribution tracking chart
    for j in range(0, len(classifications), 2):
        code = classifications.substring(j, j + 2)
        key = translateClassificationCode(code)
        if "Intro" in name:
            key = "Intro"
        if "Outro" in name:
            key = "Outro"
        if totalDamageMap.has(key):
            currentAmount = totalDamageMap.get(key)
            totalDamageMap[key] = currentAmount + totalDamage # Update the total amount
            logger.info(f'updating total damage map [{key}] by {totalDamage} (total: {currentAmount + totalDamage})')
        if key in ["Intro", "Outro"]:
            break

# Gets the percentage bonus stats from the stats input.
def getBonusStats(char1, char2, char3):
    # TODO change this to use databases instead
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Calculator")
    range = sheet.getRange("I11:L13")
    values = range.getValues()

    # Stats order should correspond to the columns I, J, K, L
    statsOrder = ["attack", "health", "defense", "energyRecharge"]

    # Character names - must match exactly with names in script
    characters = [char1, char2, char3]

    bonusStats = {}

    # Loop through each character row
    for i in range(len(characters)):
        stats = {}
        # Loop through each stat column
        for j in range(len(statsOrder)):
            stats[statsOrder[j]] = values[i][j]
        # Assign the stats object to the corresponding character
        bonusStats[characters[i]] = stats

    return bonusStats

# Handles resonance energy sharing between the party for the given skillRef and value.
def handleEnergyShare(value, activeCharacter):
    for character in characters: # energy share
        # Determine main stat amount if it is "Energy Regen"
        mainStatAmount = (
            weaponData[character]["mainStatAmount"] if weaponData[character]["mainStat"] == "Energy Regen" else 0
        )
        # Get the energy recharge from bonus stats
        bonusEnergyRecharge = bonusStats[character]["energyRecharge"]
        # Find the additional energy recharge from character data's bonus stats
        additionalEnergyRecharge = next(
            (amount for stat, amount in charData[character]["bonusStats"] if stat == "Energy Regen"), 0
        )
        # Calculate the total energy recharge
        energyRecharge = mainStatAmount + bonusEnergyRecharge + additionalEnergyRecharge
        logger.info(f'adding resonance energy to {character}; current: {charData[character]["dCond"]["Resonance"]}; value = {value}; energyRecharge = {energyRecharge}; active multiplier: {(1 if character == activeCharacter else 0.5)}')
        charData[character]["dCond"]["Resonance"] = charData[character]["dCond"]["Resonance"] + value * (1 + energyRecharge) * (1 if character == activeCharacter else 0.5)

"""
Converts a row from the ActiveEffects sheet into a dict. (Buff dict)
@param {Array} row A single row of data from the ActiveEffects sheet.
@return {dict} The row data as an dict.
"""
# TODO change name to dict
def rowToActiveEffectObject(row):
    isRegularFormat = row[7] and str(row[7]).trim() != ""
    activator = row[10] if isRegularFormat else row[6]
    if skillData[row[0]] is not None:
        activator = skillData[row[0]]["source"]
    # logger.info(f'row: {row}; regular: {isRegularFormat}')
    if isRegularFormat:
        triggeredByParsed = row[7]
        parsedCondition = None
        parsedCondition2 = None
        if "&" in row[7]:
            triggeredByParsed = row[7].split("&")[0]
            parsedCondition2 = row[7].split("&")[1]
            logger.info(f'conditions for {row[0]}; {triggeredByParsed}, {parsedCondition2}')
        elif row[1] != "Dmg" and ";" in row[7]:
            triggeredByParsed = row[7].split(";")[0]
            parsedCondition = row[7].split(";")[1]
            logger.info(f'{row[0]}; found special condition: {parsedCondition}')
        return {
            "name": row[0], # skill name
            "type": row[1], # The type of buff 
            "classifications": row[2], # The classifications this buff applies to, or All if it applies to all.
            "buffType": row[3], # The type of buff - standard, ATK buff, crit buff, elemental buff, etc
            "amount": row[4], # The value of the buff
            "duration": row[5], # How long the buff lasts - a duration is 0 indicates a passive
            "active": row[6], # Should always be TRUE
            "triggeredBy": triggeredByParsed, # The Skill, or Classification type, this buff is triggered by.
            "stackLimit": row[8] or 0, # The maximum stack limit of this buff.
            "stackInterval": row[9] or 0, # The minimum stack interval of gaining a new stack of this buff.
            "appliesTo": row[10], # The character this buff applies to, or Team in the case of a team buff
            "canActivate": activator,
            "availableIn": 0, # cooltime tracker for proc-based effects
            "specialCondition": parsedCondition,
            "additionalCondition": parsedCondition2,
            "dCond": {
                "Forte": row[11] or 0,
                "Concerto": row[12] or 0,
                "Resonance": row[13] or 0
            }
        }
    else: # short format for outros and similar
        return {
            "name": row[0],
            "type": row[1],
            "classifications": row[2],
            "buffType": row[3],
            "amount": row[4],
            "duration": row[5],
            # Assuming that for these rows, the 'active' field is not present, thus it should be assumed true
            "active": True,
            "triggeredBy": "", # No triggeredBy field for this format
            "stackLimit": 0, # Assuming 0 as default value if not present
            "stackInterval": 0, # Assuming 0 as default value if not present
            "appliesTo": row[6],
            "canActivate": activator,

            "availableIn": 0, # cooltime tracker for proc-based effects
            "specialCondition": None,
            "additionalCondition": None,
            "dCond": {
                "Forte": 0,
                "Concerto": 0,
                "Resonance": 0
            }
        }

# Turns a row from "ActiveChar" - aka, the skill data -into a skill data dict.
def rowToActiveSkillObject(row):
    # if "Intro" in row[0] or "Outro" in row[0]:
    #     return {
    #         "name": row[0], # + " (" + row[6] +")",
    #         "type": row[1],
    #         "damage": row[4],
    #         "castTime": 1.5 if "Intro" in row[0] else 0,
    #         "dps": 0,
    #         "classifications": row[2],
    #         "numberOfHits": 1,
    #         "source": row[6], # the name of the character this skill belongs to
    #         "dCond": {
    #             "Forte": row[7],
    #             "Concerto": 0,
    #             "Resonance": 0
    #         }
    #     }
    # else:
    concerto = row[8] or 0
    if row[0].startswith("Outro"):
        concerto = -100
    return {
        "name": row[0], # + " (" + row[6] +")",
        "type": "",
        "damage": row[1],
        "castTime": row[2],
        "dps": row[3],
        "classifications": row[4],
        "numberOfHits": row[5],
        "source": row[6], # the name of the character this skill belongs to
        "dCond": {
            "Forte", row[7] or 0,
            "Concerto", concerto,
            "Resonance", row[9] or 0
        },
        "freezeTime": row[10] or 0,
        "cooldown": row[11] or 0,
        "maxCharges": row[12] or 1
    }

def rowToCharacterInfo(row, levelCap):
    bonusTypes = [
        "Normal", "Heavy", "Skill", "Liberation", "Physical",
        "Glacio", "Fusion", "Electro", "Aero", "Spectro", "Havoc"
    ]

    # Map bonus names to their corresponding row values
    bonusStatsArray = [[type, row[13 + index]] for index, type in enumerate(bonusTypes)]
    bonusStatsArray.append(["Flat Attack", row[8]])
    bonusStatsArray.append(["Flat Health", row[9]])
    bonusStatsArray.append(["Flat Defense", row[10]])
    bonusStatsArray.append(["Crit", 0])
    bonusStatsArray.append(["Crit Dmg", 0])
    logger.info(row)

    critBase = min(row[11] + 0.05, 1)
    critDmgBase = row[12] + 1.5
    critBaseWeapon = 0
    critDmgBaseWeapon = 0
    build = row[7]
    charElement = CHAR_CONSTANTS[row[1]]["element"]

    #TODO move this function outside
    def updateBonusStats(array, key, value):
        # Find the index of the element where the first item matches the key
        for index, element in enumerate(array):
            if element[0] == key:
                # Update the value at the found index
                array[index][1] += value
                return  # Exit after updating to prevent unnecessary iterations
    characterName = row[1]

    if weaponData[characterName].mainStat == "Crit":
        critBaseWeapon += weaponData[characterName]["mainStatAmount"]
    if weaponData[characterName]["mainStat"] == "Crit Dmg":
        critDmgBaseWeapon += weaponData[characterName]["mainStatAmount"]
    critConditional = 0
    if characterName == "Changli" and row[2] >= 2:
        critConditional = 0.25
    match (build):
        case "43311 (ER/ER)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 350)
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 2)
            bonusStatsArray.append(['Attack', 0.18 * 2])
            bonusStatsArray.append(['Energy Regen', 0.32 * 2])
            if (critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1:
                critBase += 0.22
            else:
                critDmgBase += 0.44
        case "43311 (Ele/Ele)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 350)
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 2)
            charElementValue = next((element[1] for element in bonusStatsArray if element[0] == charElement), 0)
            updateBonusStats(bonusStatsArray, charElement, 0.6 - charElementValue)
            bonusStatsArray.append(['Attack', 0.18 * 2])
            if (critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1:
                critBase += 0.22
            else:
                critDmgBase += 0.44
        case "43311 (Ele/Atk)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 350)
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 2)
            charElementValue = next((element[1] for element in bonusStatsArray if element[0] == charElement), 0)
            updateBonusStats(bonusStatsArray, charElement, 0.3 - charElementValue)
            bonusStatsArray.append(['Attack', 0.18 * 2 + 0.3])
            if (critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1:
                critBase += 0.22
            else:
                critDmgBase += 0.44
        case "43311 (Atk/Atk)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 350)
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 2)
            bonusStatsArray.append(['Attack', 0.18 * 2 + 0.6])
            if (critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1:
                critBase += 0.22
            else:
                critDmgBase += 0.44
        case "44111 (Adaptive)":
            updateBonusStats(bonusStatsArray, 'Flat Attack', 300)
            updateBonusStats(bonusStatsArray, 'Flat Health', 2280 * 3)
            bonusStatsArray.append(['Attack', 0.18 * 3])
            for _ in range(2):
                logger.info(f'crit base: {critBaseWeapon}; crit conditional: {critConditional}; critDmgBase: {critDmgBaseWeapon}')
                if (critBase + critBaseWeapon + critConditional) * 2 < (critDmgBase + critDmgBaseWeapon) - 1:
                    critBase += 0.22
                else:
                    critDmgBase += 0.44
    logger.info(f'minor fortes: {CHAR_CONSTANTS[row[1]]["minorForte1"]}, {CHAR_CONSTANTS[row[1]]["minorForte2"]}; levelcap: {levelCap}')
    for statArray in bonusStatsArray:
        if CHAR_CONSTANTS[row[1]].minorForte1 == statArray[0]: # unlocks at rank 2/4, aka lv50/70
            if levelCap >= 70:
                statArray[1] += 0.084 * (2 / 3 if CHAR_CONSTANTS[row[1]]["minorForte1"] == "Crit" else 1)
            if levelCap >= 50:
                statArray[1] += 0.036 * (2 / 3 if CHAR_CONSTANTS[row[1]]["minorForte1"] == "Crit" else 1)
        if CHAR_CONSTANTS[row[1]].minorForte2 == statArray[0]: # unlocks at rank 3/5, aka lv60/80
            if levelCap >= 80:
                statArray[1] += 0.084 * (2 / 3 if CHAR_CONSTANTS[row[1]]["minorForte2"] == "Crit" else 1)
            if levelCap >= 60:
                statArray[1] += 0.036 * (2 / 3 if CHAR_CONSTANTS[row[1]]["minorForte2"] == "Crit" else 1)
    logger.info(f'build was: {build}; bonus stats array:')
    logger.info(bonusStatsArray)

    return {
        "name": row[1],
        "resonanceChain": row[2],
        "weapon": row[3],
        "weaponRank": row[5],
        "echo": row[6],
        "attack": CHAR_CONSTANTS[row[1]].baseAttack * WEAPON_MULTIPLIERS["levelCap"][0],
        "health": CHAR_CONSTANTS[row[1]].baseHealth * WEAPON_MULTIPLIERS["levelCap"][0],
        "defense": CHAR_CONSTANTS[row[1]].baseDef * WEAPON_MULTIPLIERS["levelCap"][0],
        "crit": critBase,
        "critDmg": critDmgBase,
        "bonusStats": bonusStatsArray,
        "dCond": {
            'Forte': 0,
            'Concerto': 0,
            'Resonance': 200 if startFullReso else 0
        }
    }

def rowToCharacterConstants(row):
    return {
        "name": row[0],
        "weapon": row[1],
        "baseHealth": row[2],
        "baseAttack": row[3],
        "baseDef": row[4],
        "minorForte1": row[5],
        "minorForte2": row[6],
        "element": row[8],
        "maxForte": row[9]
    }

def rowToWeaponInfo(row):
    return {
        "name": row[0],
        "type": row[1],
        "baseAttack": row[2],
        "baseMainStat": row[3],
        "baseMainStatAmount": row[4],
        "buff": row[5]
    }

# Turns a row from the "Echo" sheet into a dict.
def rowToEchoInfo(row):
    return {
        "name": row[0],
        "damage": row[1],
        "castTime": row[2],
        "echoSet": row[3],
        "classifications": row[4],
        "numberOfHits": row[5],
        "hasBuff": row[6],
        "cooldown": row[7],
        "dCond": {
            'Concerto': row[8] or 0,
            'Resonance': row[9] or 0
        }
    }

# Turns a row from the "EchoBuffs" sheet into a dict.
def rowToEchoBuffInfo(row):
    triggeredByParsed = row[6]
    parsedCondition2 = None
    if "&" in triggeredByParsed:
        split = triggeredByParsed.split("&")
        triggeredByParsed = split[0]
        parsedCondition2 = split[1]
        logger.info(f'conditions for echo buff {row[0]}; {triggeredByParsed}, {parsedCondition2}')
    return {
        "name": row[0],
        "type": row[1], # The type of buff 
        "classifications": row[2], # The classifications this buff applies to, or All if it applies to all.
        "buffType": row[3], # The type of buff - standard, ATK buff, crit buff, elemental buff, etc
        "amount": row[4], # The value of the buff
        "duration": row[5], # How long the buff lasts - a duration is 0 indicates a passive
        "triggeredBy": triggeredByParsed, # The Skill, or Classification type, this buff is triggered by.
        "stackLimit": row[7], # The maximum stack limit of this buff.
        "stackInterval": row[8], # The minimum stack interval of gaining a new stack of this buff.
        "appliesTo": row[9], # The character this buff applies to, or Team in the case of a team buff
        "availableIn": 0, # cooltime tracker for proc-based effects
        "additionalCondition": parsedCondition2
    }

# Creates a new echo buff object out of the given echo.
def createEchoBuff(echoBuff, character):
    newAppliesTo = character if echoBuff["appliesTo"] == "Self" else echoBuff["appliesTo"]
    return {
        "name": echoBuff["name"],
        "type": echoBuff["type"], # The type of buff 
        "classifications": echoBuff["classifications"], # The classifications this buff applies to, or All if it applies to all.
        "buffType": echoBuff["buffType"], # The type of buff - standard, ATK buff, crit buff, elemental buff, etc
        "amount": echoBuff["amount"], # The value of the buff
        "duration": echoBuff["duration"], # How long the buff lasts - a duration is 0 indicates a passive
        "triggeredBy": echoBuff["triggeredBy"], # The Skill, or Classification type, this buff is triggered by.
        "stackLimit": echoBuff["stackLimit"], # The maximum stack limit of this buff.
        "stackInterval": echoBuff["stackInterval"], # The minimum stack interval of gaining a new stack of this buff.
        "appliesTo": newAppliesTo, # The character this buff applies to, or Team in the case of a team buff
        "canActivate": character,
        "availableIn": 0, # cooltime tracker for proc-based effects
        "additionalCondition": echoBuff["additionalCondition"]
    }

# Rows of WeaponBuffs raw - these have slash-delimited values in many columns.
def rowToWeaponBuffRawInfo(row):
    triggeredByParsed = row[6]
    parsedCondition = None
    parsedCondition2 = None
    if ";" in triggeredByParsed:
        triggeredByParsed = row[6].split(";")[0]
        parsedCondition = row[6].split(";")[1]
        logger.info(f'found a special condition for {row[0]}: {parsedCondition}')
    if "&" in triggeredByParsed:
        split = triggeredByParsed.split("&")
        triggeredByParsed = split[0]
        parsedCondition2 = split[1]
        logger.info(f'conditions for weapon buff {row[0]}; {triggeredByParsed}, {parsedCondition2}')
    return {
        "name": row[0], # buff  name
        "type": row[1], # the type of buff 
        "classifications": row[2], # the classifications this buff applies to, or All if it applies to all.
        "buffType": row[3], # the type of buff - standard, ATK buff, crit buff, deepen, etc
        "amount": row[4], # slash delimited - the value of the buff
        "duration": row[5], # slash delimited - how long the buff lasts - a duration is 0 indicates a passive. for BuffEnergy, this is the Cd between procs
        "triggeredBy": triggeredByParsed, # The Skill, or Classification type, this buff is triggered by.
        "stackLimit": row[7], # slash delimited - the maximum stack limit of this buff.
        "stackInterval": row[8], # slash delimited - the minimum stack interval of gaining a new stack of this buff.
        "appliesTo": row[9], # The character this buff applies to, or Team in the case of a team buff
        "availableIn": 0, # cooltime tracker for proc-based effects
        "specialCondition": parsedCondition,
        "additionalCondition": parsedCondition2
    }

# A refined version of a weapon buff specific to a character and their weapon rank.
def rowToWeaponBuff(weaponBuff, rank, character):
    # Helper function to extract the value for a given rank
    def extractValueFromRank(valueStr, rank):
        if "/" in valueStr:
            values = valueStr.split('/')
            return float(values[rank]) if rank < len(values) else float(values[-1])
        return float(valueStr)
    
    logger.info(f'weapon buff: {weaponBuff}; amount: {weaponBuff["amount"]}')
    newAmount = extractValueFromRank(weaponBuff["amount"], rank)
    newDuration = extractValueFromRank(weaponBuff["duration"], rank)
    newStackLimit = extractValueFromRank(str(weaponBuff["stackLimit"]), rank)
    newStackInterval = extractValueFromRank(str(weaponBuff["stackInterval"]), rank)
    newAppliesTo = character if weaponBuff['appliesTo'] == "Self" else weaponBuff["appliesTo"]
    
    return {
        "name": weaponBuff["name"], # buff  name
        "type": weaponBuff["type"], # the type of buff 
        "classifications": weaponBuff["classifications"], # the classifications this buff applies to, or All if it applies to all.
        "buffType": weaponBuff["buffType"], # the type of buff - standard, ATK buff, crit buff, deepen, etc
        "amount": newAmount, # slash delimited - the value of the buff
        "active": True,
        "duration": newDuration, # slash delimited - how long the buff lasts - a duration is 0 indicates a passive
        "triggeredBy": weaponBuff["triggeredBy"], # The Skill, or Classification type, this buff is triggered by.
        "stackLimit": newStackLimit, # slash delimited - the maximum stack limit of this buff.
        "stackInterval": newStackInterval, # slash delimited - the minimum stack interval of gaining a new stack of this buff.
        "appliesTo": newAppliesTo, # The character this buff applies to, or Team in the case of a team buff
        "canActivate": character,
        "availableIn": 0, # cooltime tracker for proc-based effects
        "specialCondition": weaponBuff["specialCondition"],
        "additionalCondition": weaponBuff["additionalCondition"]
    }

# A character weapon dict.
def characterWeapon(pWeapon, pLevelCap, pRank):
    return {
        "weapon": pWeapon,
        "attack": pWeapon["baseAttack"] * WEAPON_MULTIPLIERS[pLevelCap][0],
        "mainStat": pWeapon["baseMainStat"],
        "mainStatAmount": pWeapon["baseMainStatAmount"] * WEAPON_MULTIPLIERS[pLevelCap][1],
        "rank": pRank - 1
    }

def createActiveBuff(pBuff, pTime):
    return {
        "buff": pBuff,
        "startTime": pTime,
        "stacks": 0,
        "stackTime": 0
    }

def createActiveStackingBuff(pBuff, time, pStacks):
    return {
        "buff": pBuff,
        "startTime": time,
        "stacks": pStacks,
        "stackTime": time
    }

# Creates a passive damage instance that's actively procced by certain attacks.
class PassiveDamage:
    def __init__(self, name, classifications, type, damage, duration, startTime, limit, interval, triggeredBy, owner, slot, dCond):
        self.name = name
        self.classifications = classifications
        self.type = type
        self.damage = damage
        self.duration = duration
        self.startTime = startTime
        self.limit = limit
        self.interval = interval
        self.triggeredBy = triggeredBy.split(';')[1]
        self.owner = owner
        self.slot = slot
        self.lastProc = -999
        self.numProcs = 0
        self.procMultiplier = 1
        self.totalDamage = 0
        self.totalBuffMap = []
        self.proccableBuffs = []
        self.dCond = dCond
        self.activated = False # an activation flag for TickOverTime-based effects
        self.remove = False # a flag for if a passive damage instance needs to be removed (e.g. when a new instance is added)

    def addBuff(self, buff):
        logger.info(f'adding {buff["buff"]["name"]} as a proccable buff to {self.name}')
        logger.info(buff)
        self.proccableBuffs.append(buff)

    # Handles and updates the current proc time according to the skill reference info.
    def handleProcs(self, currentTime, castTime, numberOfHits):
        procs = 0
        timeBetweenHits = castTime / (numberOfHits - 1 if numberOfHits > 1 else 1)
        # logger.info(f'handleProcs called with currentTime: {currentTime}, castTime: {castTime}, numberOfHits: {numberOfHits}')
        # logger.info(f'lastProc: {self.lastProc}, interval: {self.interval}, timeBetweenHits: {timeBetweenHits}')
        self.activated = True
        if self.interval > 0:
            if self.type == "TickOverTime":
                time = self.lastProc if self.lastProc >= 0 else currentTime
                while time <= currentTime:
                    procs += 1
                    self.lastProc = time
                    logger.info(f'Proc occurred at hitTime: {time}')
                    time += self.interval
            else:
                for hitIndex in range(numberOfHits):
                    hitTime = currentTime + timeBetweenHits * hitIndex
                    # logger.info(f'Checking hitIndex {hitIndex}: hitTime: {hitTime}, lastProc + interval: {self.lastProc + self.interval}')
                    if hitTime - self.lastProc >= self.interval:
                        procs += 1
                        self.lastProc = hitTime
                        logger.info(f'Proc occurred at hitTime: {hitTime}')
        else:
            procs = numberOfHits
        if self.limit > 0:
            procs = min(procs, self.limit - self.numProcs)
        self.numProcs += procs
        self.procMultiplier = procs
        logger.info(f'Total procs this time: {procs}')
        if procs > 0:
            for buff in self.proccableBuffs:
                buffObject = buff["buff"]
                if buffObject["type"] == "StackingBuff":
                    stacksToAdd = 1
                    stackMult = 1 + (1 if buffObject["triggeredBy"] == "Passive" and buffObject["name"].startswith("Incandescence") else 0)
                    effectiveInterval = buffObject["stackInterval"]
                    if buffObject["name"].startswith("Incandescence") and jinhsiOutroActive:
                        effectiveInterval = 1
                    if effectiveInterval < castTime: # potentially add multiple stacks
                        maxStacksByTime = (numberOfHits if effectiveInterval == 0 else castTime // effectiveInterval)
                        stacksToAdd = min(maxStacksByTime, numberOfHits)
                    logger.info(f'stacking buff {buffObject["name"]} is procced; {buffObject["triggeredBy"]}; stacks: {buff["stacks"]}; toAdd: {stacksToAdd}; mult: {stackMult}; target stacks: {min((stacksToAdd * stackMult), buffObject.stackLimit)}; interval: {effectiveInterval}')
                    buff["stacks"] = min(stacksToAdd * stackMult, buffObject["stackLimit"])
                    buff["stackTime"] = self.lastProc
                buff.startTime = self.lastProc
                queuedBuffs.append(buff)
        return procs

    def canRemove(self, currentTime, removeBuff):
        return self.numProcs >= self.limit and self.limit > 0 or (currentTime - self.startTime > self.duration) or (removeBuff and removeBuff in self.name) or self.remove

    def canProc(self, currentTime, skillRef):
        logger(f'can it proc? CT: {currentTime}; lastProc: {self.lastProc}; interval: {self.interval}')
        return currentTime + skillRef.castTime - self.lastProc >= self.interval - .01

    # Updates the total buff map to the latest local buffs.
    def updateTotalBuffMap(self):
        if lastTotalBuffMap[self.owner]:
            self.setTotalBuffMap(lastTotalBuffMap[self.owner])
        else:
            logger.info("undefined lastTotalBuffMap")

    # Sets the total buff map, updating with any skill-specific buffs.
    def setTotalBuffMap(self, totalBuffMap):
        self.totalBuffMap = dict(totalBuffMap)

        # these may have been set from the skill proccing it
        self.totalBuffMap["Specific"] = 0
        self.totalBuffMap["Deepen"] = 0
        self.totalBuffMap["Multiplier"] = 0

        for stat, value in self.totalBuffMap.items():
            if stat["name"] in stat:
                if "Specific" in stat:
                    current = self.totalBuffMap["Specific"]
                    self.totalBuffMap.set("Specific", current + value)
                    logger.info(f'updating damage bonus for {self.name} to {current} + {value}')
                elif "Multiplier" in stat:
                    current = self.totalBuffMap["Multiplier"]
                    self.totalBuffMap.set("Multiplier", current + value)
                    logger.info(f'updating damage multiplier for {self.name} to {current} + {value}')
                elif "Deepen" in stat:
                    element = reverseTranslateClassificationCode(stat.split("(")[0].trim())
                    if element in self.classifications:
                        current = self.totalBuffMap["Deepen"]
                        self.totalBuffMap.set("Deepen", current + value)
                        logger.info(f'updating damage Deepen for {self.name} to {current} + {value}')

        # the tech to apply buffs like this to passive damage effects would be a 99% unnecessary loop so i'm hardcoding this (for now) surely it's not more than a case or two
        if "Marcato" in self.name and sequences["Mortefi"] >= 3:
            self.totalBuffMap["Crit Dmg"] += 0.3

    def checkProcConditions(self, skillRef):
        logger.info(f'checking proc conditions with skill: [{self.triggeredBy}] vs {skillRef["name"]}')
        logger.info(skillRef)
        if not self.triggeredBy:
            return False
        if (self.activated and self.type == "TickOverTime") or self.triggeredBy == "Any" or (len(self.triggeredBy) > 2 and (skillRef["name"] in self.triggeredBy or self.triggeredBy in skillRef["name"])) or (len(self.triggeredBy) == 2 and self.triggeredBy in skillRef["classifications"]):
            return True
        triggeredByConditions = self.triggeredBy.split(",")
        for condition in triggeredByConditions:
            logger.info(f'checking condition: {condition}; skill ref classifications: {skillRef["classifications"]}; name: {skillRef["name"]}')
            if (len(condition) == 2 and condition in skillRef["classifications"]) or (len(condition) > 2 and (condition in skillRef["name"] or skillRef["name"] in condition)):
                return True
        logger.info("failed match")
        return False

    # Calculates a proc's damage, and adds it to the total. Also adds any relevant dynamic conditions.
    def calculateProc(self, activeCharacter):
        if self.dCond is not None:
            for value, condition in self.dCond.items():
                if value > 0:
                    logger.info(f'[PASSIVE DAMAGE] evaluating dynamic condition for {self.name}: {condition} x{value}')
                    if condition == "Resonance":
                        handleEnergyShare(value, activeCharacter)
                    else:
                        charData[activeCharacter]["dCond"][condition] = charData[activeCharacter].dCond.get(condition) + value

        bonusAttack = 0
        # if activeCharacter != self.owner:
        #     if "Stringmaster" in charData[self.owner]["weapon"]: # sorry... hardcoding just this once
        #         bonusAttack = .12 + weaponData[self.owner].rank * 0.03
        extraMultiplier = 0
        extraCritDmg = 0
        if "Marcato" in self.name:
            extraMultiplier += rythmicVibrato * 0.015
            # logger.info(f'rythmic vibrato count: {rythmicVibrato}')

        totalBuffMap = self.totalBuffMap
        attack = (charData[self.owner]["attack"] + weaponData[self.owner]["attack"]) * (1 + totalBuffMap["Attack"] + bonusStats[self.owner]["attack"] + bonusAttack) + totalBuffMap["Flat Attack"]
        health = (charData[self.owner]["health"]) * (1 + totalBuffMap["Health"] + bonusStats[self.owner]["health"]) + totalBuffMap["Flat Health"]
        defense = (charData[self.owner]["defense"]) * (1 + totalBuffMap["Defense"] + bonusStats[self.owner]["defense"]) + totalBuffMap["Flat Defense"]
        critMultiplier = (1 - min(1, (charData[self.owner]["crit"] + totalBuffMap["Crit"]))) * 1 + min(1, (charData[self.owner]["crit"] + totalBuffMap["Crit"])) * (charData[self.owner]["critDmg"] + totalBuffMap["Crit Dmg"] + extraCritDmg)
        damageMultiplier = getDamageMultiplier(self.classifications, totalBuffMap) + extraMultiplier

        additiveValueKey = f'{self.name} (Additive)'
        rawDamage = self.damage * (1 if self.name.startswith("Jué") else skillLevelMultiplier) + (totalBuffMap[additiveValueKey] if additiveValueKey in totalBuffMap else 0)

        # logger.info(f'{rawDamage} / {additiveValueKey}:  {additiveValueKey in totalBuffMap} / {totalBuffMap[additiveValueKey] if additiveValueKey in totalBuffMap else 0}')

        scaleFactor = defense if "Df" in self.classifications else (health if "Hp" in self.classifications else attack)
        totalDamage = rawDamage * scaleFactor * critMultiplier * damageMultiplier * (0 if weaponData[self.owner]["weapon"]["name"] == "Nullify Damage" else 1)
        logger.info(f'passive proc damage: {rawDamage:.2f}; attack: {(charData[self.owner]["attack"] + weaponData[self.owner]["attack"]):.2f} x {(1 + totalBuffMap["Attack"] + bonusStats[self.owner]["attack"]):.2f}; crit mult: {critMultiplier:.2f}; dmg mult: {damageMultiplier:.2f}; total dmg: {totalDamage:.2f}')
        self.totalDamage += totalDamage * self.procMultiplier
        updateDamage(self.name, self.classifications, self.owner, rawDamage * self.procMultiplier, totalDamage * self.procMultiplier, totalBuffMap, extraMultiplier)
        self.procMultiplier = 1
        return totalDamage

    # Returns a note to place on the cell.
    # TODO change this to use databases instead
    def getNote(self):
        additiveValueKey = f'{self.name} (Additive)'
        if self.limit == 1:
            if self.name == "Star Glamour" and sequences["Jinhsi"] >= 2: # todo...
                return f'This skill triggered an additional damage effect: {self.name}, dealing {self.totalDamage:.2f} DMG (Base Ratio: {(self.damage * 100):.2f}%  x {skillLevelMultiplier:.2f} + {(self.totalBuffMap[additiveValueKey] * 100 if additiveValueKey in self.totalBuffMap else 0)}%).'
            return f'This skill triggered an additional damage effect: {self.name}, dealing {self.totalDamage:.2f} DMG (Base Ratio: {(self.damage * 100):.2f}%  x {skillLevelMultiplier:.2f} + {(self.totalBuffMap[additiveValueKey] * 100 if additiveValueKey in self.totalBuffMap else 0)}%).'
        if self.type == "TickOverTime":
            if self.name.startswith("Jué"):
                return f'This skill triggered a passive DOT effect: {self.name}, which has ticked {self.numProcs} times for {self.totalDamage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% + {(self.totalBuffMap[additiveValueKey] * 100 if additiveValueKey in self.totalBuffMap else 0):.2f}%).'
            return f'This skill triggered a passive DOT effect: {self.name}, which has ticked {self.numProcs} times for {self.totalDamage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% x {skillLevelMultiplier:.2f} + {(self.totalBuffMap[additiveValueKey] * 100 if additiveValueKey in self.totalBuffMap else 0):.2f}%).'
        return f'This skill triggered a passive damage effect: {self.name}, which has procced {self.numProcs} times for {self.totalDamage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% x {skillLevelMultiplier:.2f} + {(self.totalBuffMap[additiveValueKey] * 100 if additiveValueKey in self.totalBuffMap else 0):.2f}%).'

# Extracts the skill reference from the skillData object provided, with the name of the current character.
# Skill data objects have a (Character) name at the end of them to avoid duplicates. Jk, now they don't, but all names MUST be unique.
def getSkillReference(skillData, name, character):
    return skillData[name] # + " (" + character + ")"

def removeTextWithinParentheses(inputString):
    while '(' in inputString and ')' in inputString:
        start = inputString.find('(')
        end = inputString.find(')', start) + 1
        inputString = inputString[:start] + inputString[end:]
    return inputString.strip()

def extractNumberAfterX(inputString):
    xIndex = inputString.find('x')
    
    if xIndex == -1:
        return None

    numberStartIndex = xIndex + 1

    # Check if the character after 'x' is a digit
    if numberStartIndex < len(inputString) and inputString[numberStartIndex].isdigit():
        numberEndIndex = numberStartIndex

        # Find the end of the digit sequence
        while numberEndIndex < len(inputString) and inputString[numberEndIndex].isdigit():
            numberEndIndex += 1

        return int(inputString[numberStartIndex:numberEndIndex])

    return None

def reverseTranslateClassificationCode(code):
    classifications = {
        "Normal": "No",
        "Heavy": "He",
        "Skill": "Sk",
        "Liberation": "Rl",
        "Glacio": "Gl",
        "Spectro": "Sp",
        "Fusion": "Fu",
        "Electro": "El",
        "Aero": "Ae",
        "Spectro": "Sp",
        "Havoc": "Ha",
        "Physical": "Ph",
        "Echo": "Ec",
        "Outro": "Ou",
        "Intro": "In"
    }
    return classifications[code] or code # Default to code if not found

def translateClassificationCode(code):
    classifications = {
        "No": "Normal",
        "He": "Heavy",
        "Sk": "Skill",
        "Rl": "Liberation",
        "Gl": "Glacio",
        "Sp": "Spectro",
        "Fu": "Fusion",
        "El": "Electro",
        "Ae": "Aero",
        "Sp": "Spectro",
        "Ha": "Havoc",
        "Ph": "Physical",
        "Ec": "Echo",
        "Ou": "Outro",
        "In": "Intro"
    }
    return classifications[code] or code # Default to code if not found

def getDamageMultiplier(classification, totalBuffMap):
    damageMultiplier = 1
    damageBonus = 1
    damageDeepen = 0
    # TODO change this to use databases instead
    res = rotationSheet.getRange("D5").getValue()
    enemyLevel = rotationSheet.getRange("H4").getValue()
    levelCap = rotationSheet.getRange("F4").getValue()
    enemyDefense = 792 + 8 * enemyLevel
    defPen = totalBuffMap["Ignore Defense"]
    defenseMultiplier = (800 + levelCap * 8) / (enemyDefense * (1 - defPen) + 800 + levelCap * 8)
    # logger.info(f'defenseMultiplier: {defenseMultiplier}')
    resShred = totalBuffMap.get("Resistance")
    # loop through each pair of characters in the classification string
    for i in range(0, len(classification), 2):
        code = classification[i:i + 2]
        classificationName = translateClassificationCode(code)
        # if classification is in the totalBuffMap, apply its buff amount to the damage multiplier
        if classificationName in totalBuffMap:
            if classificationName in STANDARD_BUFF_TYPES: # check for deepen effects as well
                deepenName = f'{classificationName} (Deepen)'
                if deepenName in totalBuffMap:
                    damageDeepen += totalBuffMap.get(deepenName)
                damageBonus += totalBuffMap[classificationName]
            else:
                damageBonus += totalBuffMap[classificationName]
    resMultiplier = 1
    if res <= 0: # resistance multiplier calculation
        resMultiplier = 1 - (res - resShred) / 2
    elif res < .8:
        resMultiplier = 1 - (res - resShred)
    else:
        resMultiplier = 1 / (1 + (res - resShred) * 5)
    # logger.info(f'res multiplier: {resMultiplier}')
    damageDeepen += totalBuffMap["Deepen"]
    damageBonus += totalBuffMap["Specific"]
    logger.info(f'damage multiplier: (BONUS={damageBonus}) * (MULTIPLIER=1 + {totalBuffMap["Multiplier"]}) * (DEEPEN=1 + {damageDeepen}) * (RES={resMultiplier}) * (DEF={defenseMultiplier})')
    return damageMultiplier * damageBonus * (1 + totalBuffMap["Multiplier"]) * (1 + damageDeepen) * resMultiplier * defenseMultiplier

# Loads skills from the calculator "ActiveChar" sheet.
def getSkills(): # TODO change this to use databases instead
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("ActiveChar")
    range = sheet.getDataRange()
    values = range.getValues()

    # filter rows where the first cell is not empty
    filteredValues = [row for row in values if row[0].strip() != ""] # Ensure that the name is not empty

    objects = [rowToActiveSkillObject(row) for row in filteredValues]
    return objects

def getActiveEffects(): # TODO change this to use databases instead
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("ActiveEffects")
    range = sheet.getDataRange()
    values = range.getValues()

    objects = [rowToActiveEffectObject(row) for row in values if rowToActiveEffectObject(row) is not None]
    return objects

def getWeapons(): # TODO change this to use databases instead
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Weapons")
    range = sheet.getDataRange()
    values = range.getValues()

    weaponsMap = {}

    # Start loop at 1 to skip header row
    for i in range(1, len(values)):
        if values[i][0]: # Check if the row actually contains a weapon name
            weaponInfo = rowToWeaponInfo(values[i])
            weaponsMap[weaponInfo["name"]] = weaponInfo # Use weapon name as the key for lookup

    return weaponsMap

def getEchoes(): # TODO change this to use databases instead
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Echo")
    range = sheet.getDataRange()
    values = range.getValues()

    echoMap = {}

    for i in range(1, len(values)):
        if (values[i][0]): # check if the row actually contains an echo name
            echoInfo = rowToEchoInfo(values[i])
            echoMap[echoInfo["name"]] = echoInfo # Use echo name as the key for lookup

    return echoMap

"""
Exports the build.
Format:
Friendly Name; CSV Stats & Bonus Stats; Stats 2; Stats 3; CSV Rotation (Format: Character&Skill)

Example:
S1R1 Jinhsi + Ages of Harvest / ... ; 100,0,0,43%,81%,...; [x3] Jinshi&Skill: Test,Jinshi&Basic: Test2
"""
def exportBuild():
    characters = []
    charInfo = []
    charInfoRaw = []
    bonusStats = []
    buildString = ""
    for i in range(7, 10): # TODO change this to use databases instead
        character = rotationSheet.getRange(f'B{i}').getValue()
        characters.append(character)
        charInfo.append(rowToCharacterInfoRaw(rotationSheet.getRange(f'A{i}:Z{i}').getValues()[0]))
        charInfoRaw.append(rotationSheet.getRange(f'B{i}:Z{i}').getValues()[0])
        bonusStats.append(rotationSheet.getRange(f'I{i + 4}:L{i + 4}').getValues()[0])
    divider = ""
    for i in range(len(characters)):
        buildString += divider
        buildString += "S"
        buildString += charInfo[i]["resonanceChain"]
        buildString += "R"
        buildString += charInfo[i]["weaponRank"]
        buildString += " "
        buildString += characters[i]
        buildString += " + "
        buildString += charInfo[i]["weapon"]
        divider = " / "
    buildString += ";"
    divider2 = ""
    for i in range(len(characters)):
        buildString += divider2
        divider = ""
        for j in range(len(charInfoRaw[i])):
            buildString += divider
            buildString += charInfoRaw[i][j]
            divider = ","
        for j in range(len(bonusStats[i])):
            buildString += divider
            buildString += bonusStats[i][j]
            divider = ","
        divider2 = ";"
    buildString += ";"

    divider = ""
    for i in range(ROTATION_START, ROTATION_END + 1): # TODO change this to use databases instead
        character = rotationSheet.getRange("A" + i).getValue()
        skill = rotationSheet.getRange("B" + i).getValue()
        if not character or not skill:
            break
        buildString += divider
        buildString += character
        buildString += "&"
        buildString += skill
        divider = ","
    rotationSheet.getRange("K23").setValue(buildString) # TODO change this to use databases instead

    # save the previous execution to the first open slot
    if rotationSheet.getRange("H28").getValue() > 0: # TODO change this to use databases instead
        library = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Build Library')
        for i in range(10, 1000):
            if library.getRange(f'M{i}').getValue():
                continue
            data = [ # TODO change this to use databases instead
                [
                    characters[0],
                    characters[1],
                    characters[2],
                    rotationSheet.getRange("H27").getValue(),
                    rotationSheet.getRange("H28").getValue(),
                    rotationSheet.getRange("H29").getValue(),
                    buildString
                ]
            ]

            rowRange = library.getRange(f'M{i}:S{i}'); # TODO change this to use databases instead
            rowRange.setValues(data)
            break

# Turns a row into a raw character data info for build exporting.
def rowToCharacterInfoRaw(row):
    return {
        "name": row[1],
        "resonanceChain": row[2],
        "weapon": row[3],
        "weaponRank": row[5],
        "echo": row[6],
        "build": row[7],
        "attack": row[8],
        "health": row[9],
        "defense": row[10],
        "crit": row[11],
        "critDmg": row[12],
        "normal": row[13],
        "heavy": row[14],
        "skill": row[15],
        "liberation": row[16]
    }

def test():
    effects = getActiveEffects()
    for effect in effects:
        logger.debug(
            f'Name: {effect["name"]}'
            f', Type: {effect["type"]}'
            f', Classifications: {effect["classifications"]}'
            f', Buff Type: {effect["buffType"]}'
            f', Amount: {effect["amount"]}'
            f', Duration: {effect["duration"]}'
            f', Active: {effect["active"]}'
            f', Triggered By: {effect["triggeredBy"]}'
            f', Stack Limit: {effect["stackLimit"]}'
            f', Stack Interval: {effect["stackInterval"]}'
        )