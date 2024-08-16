import logging
from copy import deepcopy
from functools import cmp_to_key
from utils.database_io import fetch_data_comparing_two_databases, fetch_data_from_database, initialize_database, overwrite_table_data, overwrite_table_data_by_row_ids
from utils.config_io import load_config
from config.constants import CALCULATOR_DB_PATH, CONFIG_PATH, CONSTANTS_DB_PATH, CHARACTERS_DB_PATH

logger = logging.getLogger(__name__)

CHECK_STATS = True

STANDARD_BUFF_TYPES = ["Normal", "Heavy", "Skill", "Liberation"]
ELEMENTAL_BUFF_TYPES = ["Glacio", "Fusion", "Electro", "Aero", "Spectro", "Havoc"]

def initialize_calc_tables(db_name=CALCULATOR_DB_PATH):
    """
    Initialize database tables based on configuration settings.

    This function loads the configuration from a JSON file and initializes each table
    specified in the configuration. For each table, it will create the table if it does
    not already exist and optionally insert initial data if provided.

    :param db_name:
        The path to the database file where tables will be initialized. 
        Defaults to `CALCULATOR_DB_PATH`.
    :type db_name: str, optional

    :raises FileNotFoundError: If the configuration file is not found at the specified path.
    :raises KeyError: If the database name is not found in the configuration file.
    :raises Exception: If there is an issue with loading the configuration or initializing tables.

    :return: None
    """
    config = load_config(CONFIG_PATH)
    tables = config.get(db_name)["tables"]
    for table in tables:
        initialize_database(db_name, table["table_name"], table["db_columns"], initial_data=table.get("initial_data", None))

initialize_calc_tables()

def get_weapon_multipliers(db_name=CONSTANTS_DB_PATH, table_name="WeaponMultipliers"):
    """
    Retrieve weapon multipliers from the specified database table.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :return: A dictionary of weapon multipliers with levels as keys.
    :rtype: dict
    """
    data = fetch_data_from_database(db_name, table_name, columns=["Level", "ATK", "MainStat"])
    
    return {column[0]: [column[1], column[2]] for column in data}

WEAPON_MULTIPLIERS = get_weapon_multipliers()

def row_to_character_constants(row):
    """
    Convert a row of data into character constants.

    :param row: The data row to convert.
    :type row: list
    :return: A dictionary representing character constants.
    :rtype: dict
    """
    return {
        "name": row[0],
        "weapon": row[1],
        "base_health": row[2],
        "base_attack": row[3],
        "base_def": row[4],
        "minor_forte1": row[5],
        "minor_forte2": row[6],
        "element": row[8],
        "max_forte": row[9]
    }

def get_character_constants(db_name=CONSTANTS_DB_PATH, table_name="CharacterConstants"):
    """
    Retrieve character constants from the specified database table.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :return: A dictionary of character constants with character names as keys.
    :rtype: dict
    """
    data = fetch_data_from_database(db_name, table_name)

    char_constants = {}
    
    for row in data:
        if row[0]:  # check if the row actually contains a name
            char_info = row_to_character_constants(row)
            char_constants[char_info["name"]] = char_info  # use character name as the key for lookup
        else:
            break

    return char_constants

CHAR_CONSTANTS = get_character_constants()

skill_data = {}
passive_damage_instances = []
weapon_data = {}
char_data = {}
characters = []
sequences = {}
lastTotalBuffMap = {} # the last updated total buff maps for each character
bonus_stats = {}
queued_buffs = []

def get_skill_level_multiplier(
    constants_db_name=CONSTANTS_DB_PATH, constants_table_name="SkillLevels", 
    calculator_db_name=CALCULATOR_DB_PATH, calculator_table_name="Settings"):
    """
    Retrieve the skill level multiplier from the specified database table depending on the skill level chosen.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :return: The skill level multiplier.
    :rtype: float
    """
    return fetch_data_comparing_two_databases(
        constants_db_name, constants_table_name, 
        calculator_db_name, calculator_table_name, 
        columns1="Value", columns2="", 
        where_clause="t1.Level = t2.SkillLevel"
        )[0][0]

skill_level_multiplier = get_skill_level_multiplier()

# The "Opener" damage is the total damage dealt before the first main DPS (first character) executes their Outro for the first time.
opener_damage = 0
opener_time = 0
loop_damage = 0
mode = "Opener"

jinhsi_outro_active = False
rythmic_vibrato = 0

start_full_reso = False

level_cap, enemy_level, res = fetch_data_from_database(CALCULATOR_DB_PATH, "Settings", columns=["LevelCap", "EnemyLevel", "Resistance"])[0]

# Data for stat analysis
stat_check_map = {
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
char_stat_gains = {}
char_entries = {}
total_damage_map = {
    "Normal": 0,
    "Heavy": 0,
    "Skill": 0,
    "Liberation": 0,
    "Intro": 0,
    "Outro": 0,
    "Echo": 0
}
damage_by_character = {}

def row_to_weapon_info(row):
    """
    Convert a row of data into weapon information.

    :param row: The data row to convert.
    :type row: list
    :return: A dictionary representing weapon information.
    :rtype: dict
    """
    return {
        "name": row[0],
        "type": row[1],
        "base_attack": row[2],
        "base_main_stat": row[3],
        "base_main_stat_amount": row[4],
        "buff": row[5]
    }

def row_to_echo_info(row):
    """
    Convert a row of data into echo information.

    :param row: The data row to convert.
    :type row: list
    :return: A dictionary representing echo information.
    :rtype: dict
    """
    return {
        "name": row[0],
        "damage": row[1],
        "cast_time": row[2],
        "echo_set": row[3],
        "classifications": row[4],
        "number_of_hits": row[5],
        "has_buff": row[6],
        "cooldown": row[7],
        "d_cond": {
            'concerto': row[8] or 0,
            'resonance': row[9] or 0
        }
    }

def row_to_echo_buff_info(row):
    """
    Convert a row of data into echo buff information.

    :param row: The data row to convert.
    :type row: list
    :return: A dictionary representing echo buff information.
    :rtype: dict
    """
    triggered_by_parsed = row[6]
    parsed_condition2 = None
    if "&" in triggered_by_parsed:
        split = triggered_by_parsed.split("&")
        triggered_by_parsed = split[0]
        parsed_condition2 = split[1]
        logger.info(f'conditions for echo buff {row[0]}; {triggered_by_parsed}, {parsed_condition2}')
    return {
        "name": row[0],
        "type": row[1], # The type of buff 
        "classifications": row[2], # The classifications this buff applies to, or All if it applies to all.
        "buff_type": row[3], # The type of buff - standard, ATK buff, crit buff, elemental buff, etc
        "amount": row[4], # The value of the buff
        "duration": row[5], # How long the buff lasts - a duration is 0 indicates a passive
        "triggered_by": triggered_by_parsed, # The Skill, or Classification type, this buff is triggered by.
        "stack_limit": row[7], # The maximum stack limit of this buff.
        "stack_interval": row[8], # The minimum stack interval of gaining a new stack of this buff.
        "applies_to": row[9], # The character this buff applies to, or Team in the case of a team buff
        "available_in": 0, # cooltime tracker for proc-based effects
        "additionalCondition": parsed_condition2
    }

def create_echo_buff(echo_buff, character):
    """
    Create a new echo buff dictionary out of the given echo.

    :param echo_buff: The echo buff information.
    :type echo_buff: dict
    :param character: The character the buff applies to.
    :type character: str
    :return: A dictionary representing the new echo buff.
    :rtype: dict
    """
    new_applies_to = character if echo_buff["applies_to"] == "Self" else echo_buff["applies_to"]
    return {
        "name": echo_buff["name"],
        "type": echo_buff["type"], # The type of buff 
        "classifications": echo_buff["classifications"], # The classifications this buff applies to, or All if it applies to all.
        "buff_type": echo_buff["buff_type"], # The type of buff - standard, ATK buff, crit buff, elemental buff, etc
        "amount": echo_buff["amount"], # The value of the buff
        "duration": echo_buff["duration"], # How long the buff lasts - a duration is 0 indicates a passive
        "triggered_by": echo_buff["triggered_by"], # The Skill, or Classification type, this buff is triggered by.
        "stack_limit": echo_buff["stack_limit"], # The maximum stack limit of this buff.
        "stack_interval": echo_buff["stack_interval"], # The minimum stack interval of gaining a new stack of this buff.
        "applies_to": new_applies_to, # The character this buff applies to, or Team in the case of a team buff
        "can_activate": character,
        "available_in": 0, # cooltime tracker for proc-based effects
        "additionalCondition": echo_buff["additionalCondition"]
    }

def row_to_weapon_buff_raw_info(row):
    """
    Convert a row of data into raw weapon buff information.

    :param row: The data row to convert.
    :type row: list
    :return: A dictionary representing raw weapon buff information.
    :rtype: dict
    """
    triggered_by_parsed = row[6]
    parsed_condition = None
    parsed_condition2 = None
    if ";" in triggered_by_parsed:
        triggered_by_parsed = row[6].split(";")[0]
        parsed_condition = row[6].split(";")[1]
        logger.info(f'found a special condition for {row[0]}: {parsed_condition}')
    if "&" in triggered_by_parsed:
        split = triggered_by_parsed.split("&")
        triggered_by_parsed = split[0]
        parsed_condition2 = split[1]
        logger.info(f'conditions for weapon buff {row[0]}; {triggered_by_parsed}, {parsed_condition2}')
    return {
        "name": row[0], # buff  name
        "type": row[1], # the type of buff 
        "classifications": row[2], # the classifications this buff applies to, or All if it applies to all.
        "buff_type": row[3], # the type of buff - standard, ATK buff, crit buff, deepen, etc
        "amount": row[4], # slash delimited - the value of the buff
        "duration": row[5], # slash delimited - how long the buff lasts - a duration is 0 indicates a passive. for BuffEnergy, this is the Cd between procs
        "triggered_by": triggered_by_parsed, # The Skill, or Classification type, this buff is triggered by.
        "stack_limit": row[7], # slash delimited - the maximum stack limit of this buff.
        "stack_interval": row[8], # slash delimited - the minimum stack interval of gaining a new stack of this buff.
        "applies_to": row[9], # The character this buff applies to, or Team in the case of a team buff
        "available_in": 0, # cooltime tracker for proc-based effects
        "special_condition": parsed_condition,
        "additional_condition": parsed_condition2
    }

def extract_value_from_rank(value_str, rank):
    """
    Extract the value for a given rank from a slash-delimited string.

    This function takes a string containing slash-delimited values and extracts the value corresponding to the given rank.
    If the rank is out of bounds, it returns the last value in the string. If the input string is not slash-delimited, it returns the value as a float.

    :param value_str: The slash-delimited string containing values.
    :type value_str: str
    :param rank: The rank for which the value is to be extracted.
    :type rank: int
    :return: The extracted value as a float.
    :rtype: float
    """
    if "/" in value_str:
        values = value_str.split('/')
        return float(values[rank]) if rank < len(values) else float(values[-1])
    return float(value_str)

def row_to_weapon_buff(weapon_buff, rank, character):
    """
    Convert a raw weapon buff into a refined weapon buff specific to a character and their weapon rank.

    :param weapon_buff: The raw weapon buff information.
    :type weapon_buff: dict
    :param rank: The weapon rank.
    :type rank: int
    :param character: The character the buff applies to.
    :type character: str
    :return: A dictionary representing the refined weapon buff.
    :rtype: dict
    """
    logger.info(f'weapon buff: {weapon_buff}; amount: {weapon_buff["amount"]}')
    new_amount = extract_value_from_rank(weapon_buff["amount"], rank)
    new_duration = extract_value_from_rank(weapon_buff["duration"], rank)
    new_stack_limit = extract_value_from_rank(str(weapon_buff["stack_limit"]), rank)
    new_stack_interval = extract_value_from_rank(str(weapon_buff["stack_interval"]), rank)
    new_applies_to = character if weapon_buff['applies_to'] == "Self" else weapon_buff["applies_to"]
    
    return {
        "name": weapon_buff["name"], # buff  name
        "type": weapon_buff["type"], # the type of buff 
        "classifications": weapon_buff["classifications"], # the classifications this buff applies to, or All if it applies to all.
        "buff_type": weapon_buff["buffType"], # the type of buff - standard, ATK buff, crit buff, deepen, etc
        "amount": new_amount, # slash delimited - the value of the buff
        "active": True,
        "duration": "Passive" if weapon_buff["duration"] in ("Passive", 0) else new_duration, # slash delimited - how long the buff lasts - a duration is 0 indicates a passive
        "triggered_by": weapon_buff["triggered_by"], # The Skill, or Classification type, this buff is triggered by.
        "stack_limit": new_stack_limit, # slash delimited - the maximum stack limit of this buff.
        "stack_interval": new_stack_interval, # slash delimited - the minimum stack interval of gaining a new stack of this buff.
        "applies_to": new_applies_to, # The character this buff applies to, or Team in the case of a team buff
        "can_activate": character,
        "available_in": 0, # cooltime tracker for proc-based effects
        "special_condition": weapon_buff["special_condition"],
        "additional_condition": weapon_buff["additional_condition"]
    }

def character_weapon(p_weapon, p_level_cap, p_rank):
    """
    Create a character weapon dictionary.

    :param p_weapon: The weapon information.
    :type p_weapon: dict
    :param p_level_cap: The level cap of the weapon.
    :type p_level_cap: int
    :param p_rank: The rank of the weapon.
    :type p_rank: int
    :return: A dictionary representing the character weapon.
    :rtype: dict
    """
    return {
        "weapon": p_weapon,
        "attack": p_weapon["base_attack"] * WEAPON_MULTIPLIERS[p_level_cap][0],
        "main_stat": p_weapon["base_main_stat"],
        "main_stat_amount": p_weapon["base_main_stat_amount"] * WEAPON_MULTIPLIERS[p_level_cap][1],
        "rank": p_rank - 1
    }

def create_active_buff(p_buff, p_time):
    """
    Create an active buff dictionary.

    :param p_buff: The buff information.
    :type p_buff: dict
    :param p_time: The time the buff becomes active.
    :type p_time: float
    :return: A dictionary representing the active buff.
    :rtype: dict
    """
    return {
        "buff": p_buff,
        "start_time": p_time,
        "stacks": 0,
        "stack_time": 0
    }

def create_active_stacking_buff(p_buff, time, p_stacks):
    """
    Create an active stacking buff dictionary.

    :param p_buff: The buff information.
    :type p_buff: dict
    :param time: The time the buff becomes active.
    :type time: float
    :param p_stacks: The number of stacks the buff starts with.
    :type p_stacks: int
    :return: A dictionary representing the active stacking buff.
    :rtype: dict
    """
    return {
        "buff": p_buff,
        "start_time": time,
        "stacks": p_stacks,
        "stack_time": time
    }

# Gets the percentage bonus stats from the stats input.
def get_bonus_stats(char1, char2, char3):
    values = fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", columns=["AttackPercent", "HealthPercent", "DefensePercent", "EnergyRegen"])

    # Stats order should correspond to the columns I, J, K, L
    stats_order = ["attack", "health", "defense", "energy_recharge"]

    # Character names - must match exactly with names in script
    characters = [char1, char2, char3]

    bonus_stats = {}

    # Loop through each character row
    for i in range(len(characters)):
        # Loop through each stat column
        stats = {stats_order[j]: values[i][j] for j in range(len(stats_order))}
        # Assign the stats object to the corresponding character
        bonus_stats[characters[i]] = stats

    return bonus_stats

def get_weapons():
    values = fetch_data_from_database(CONSTANTS_DB_PATH, "Weapons")

    weapons_map = {}

    # Start loop at 1 to skip header row
    for i in range(1, len(values)):
        if values[i][0]: # Check if the row actually contains a weapon name
            weapon_info = row_to_weapon_info(values[i])
            weapons_map[weapon_info["name"]] = weapon_info # Use weapon name as the key for lookup

    return weapons_map

def get_echoes():
    values = fetch_data_from_database(CONSTANTS_DB_PATH, "Echoes")

    echo_map = {}

    for i in range(1, len(values)):
        if (values[i][0]): # check if the row actually contains an echo name
            echo_info = row_to_echo_info(values[i])
            echo_map[echo_info["name"]] = echo_info # Use echo name as the key for lookup

    return echo_map

def update_bonus_stats(dict, key, value):
    # Find the index of the element where the first item matches the key
    for index, element in enumerate(dict):
        if element[0] == key:
            # Update the value at the found index
            dict[index][1] += value
            return  # Exit after updating to prevent unnecessary iterations

def row_to_character_info(row, level_cap):
    global weapon_data
    # Map bonus names to their corresponding row values
    bonus_stats_dict = {
        "flat_attack": row[6],
        "flat_health": row[8],
        "flat_defense": row[10],
        "crit_rate": 0,
        "crit_dmg": 0,
        "normal": 0,
        "heavy": 0,
        "skill": 0,
        "liberation": 0,
        "physical": 0,
        "glacio": 0,
        "fusion": 0,
        "electro": 0,
        "aero": 0,
        "spectro": 0,
        "havoc": 0
    }
    logger.info(row)

    crit_rate_base = min(row[12] + 0.05, 1)
    crit_dmg_base = row[13] + 1.5
    crit_rate_base_weapon = 0
    crit_dmg_base_weapon = 0
    build = row[5]
    char_element = CHAR_CONSTANTS[row[0]]["element"]

    character_name = row[0]

    match weapon_data[character_name]["main_stat"]:
        case "crit_rate":
            crit_rate_base_weapon += weapon_data[character_name]["main_stat_amount"]
        case "crit_dmg":
            crit_dmg_base_weapon += weapon_data[character_name]["main_stat_amount"]
    crit_rate_conditional = 0
    if character_name == "Changli" and row[1] >= 2:
        crit_rate_conditional = 0.25
    match build:
        case "43311 (ER/ER)":
            update_bonus_stats(bonus_stats_dict, "flat_attack", 350)
            update_bonus_stats(bonus_stats_dict, "flat_health", 2280 * 2)
            bonus_stats_dict["attack"] = 0.18 * 2
            bonus_stats_dict["energy_regen"] = 0.32 * 2
            if (
                crit_rate_base + crit_rate_base_weapon + crit_rate_conditional
            ) * 2 < (crit_dmg_base + crit_dmg_base_weapon) - 1:
                crit_rate_base += 0.22
            else:
                crit_dmg_base += 0.44
        case "43311 (Ele/Ele)":
            update_bonus_stats(bonus_stats_dict, "flat_attack", 350)
            update_bonus_stats(bonus_stats_dict, "flat_health", 2280 * 2)
            char_element_value = next((element[1] for element in bonus_stats_dict if element[0] == char_element), 0)
            update_bonus_stats(bonus_stats_dict, char_element, 0.6 - char_element_value)
            bonus_stats_dict["attack"] = 0.18 * 2
            if (
                crit_rate_base + crit_rate_base_weapon + crit_rate_conditional
            ) * 2 < (crit_dmg_base + crit_dmg_base_weapon) - 1:
                crit_rate_base += 0.22
            else:
                crit_dmg_base += 0.44
        case "43311 (Ele/Atk)":
            update_bonus_stats(bonus_stats_dict, "flat_attack", 350)
            update_bonus_stats(bonus_stats_dict, "flat_health", 2280 * 2)
            char_element_value = next((element[1] for element in bonus_stats_dict if element[0] == char_element), 0)
            update_bonus_stats(bonus_stats_dict, char_element, 0.3 - char_element_value)
            bonus_stats_dict["attack"] = 0.18 * 2 + 0.3
            if (
                crit_rate_base + crit_rate_base_weapon + crit_rate_conditional
            ) * 2 < (crit_dmg_base + crit_dmg_base_weapon) - 1:
                crit_rate_base += 0.22
            else:
                crit_dmg_base += 0.44
        case "43311 (Atk/Atk)":
            update_bonus_stats(bonus_stats_dict, "flat_attack", 350)
            update_bonus_stats(bonus_stats_dict, "flat_health", 2280 * 2)
            bonus_stats_dict["attack"] = 0.18 * 2 + 0.6
            if (
                crit_rate_base + crit_rate_base_weapon + crit_rate_conditional
            ) * 2 < (crit_dmg_base + crit_dmg_base_weapon) - 1:
                crit_rate_base += 0.22
            else:
                crit_dmg_base += 0.44
        case "44111 (Adaptive)":
            update_bonus_stats(bonus_stats_dict, "flat_attack", 300)
            update_bonus_stats(bonus_stats_dict, "flat_health", 2280 * 3)
            bonus_stats_dict["attack"] = 0.18 * 3
            for _ in range(2):
                logger.info(
                    f'crit rate base: {crit_rate_base_weapon}; crit rate conditional: '
                    f'{crit_rate_conditional}; crit dmg base: {crit_dmg_base_weapon}'
                )
                if (
                    crit_rate_base + crit_rate_base_weapon + crit_rate_conditional
                ) * 2 < (crit_dmg_base + crit_dmg_base_weapon) - 1:
                    crit_rate_base += 0.22
                else:
                    crit_dmg_base += 0.44
    logger.info(f'minor fortes: {CHAR_CONSTANTS[row[0]]["minor_forte1"]}, {CHAR_CONSTANTS[row[0]]["minor_forte2"]}; level cap: {level_cap}')
    for stat_array in bonus_stats_dict:
        if CHAR_CONSTANTS[row[0]]["minor_forte1"] == stat_array[0]: # unlocks at rank 2/4, aka lv50/70
            if level_cap >= 70:
                stat_array[1] += 0.084 * (2 / 3 if CHAR_CONSTANTS[row[0]]["minor_forte1"] == "crit_rate" else 1)
            if level_cap >= 50:
                stat_array[1] += 0.036 * (2 / 3 if CHAR_CONSTANTS[row[0]]["minor_forte1"] == "crit_rate" else 1)
        if CHAR_CONSTANTS[row[0]]["minor_forte2"] == stat_array[0]: # unlocks at rank 3/5, aka lv60/80
            if level_cap >= 80:
                stat_array[1] += 0.084 * (2 / 3 if CHAR_CONSTANTS[row[0]]["minor_forte2"] == "crit_rate" else 1)
            if level_cap >= 60:
                stat_array[1] += 0.036 * (2 / 3 if CHAR_CONSTANTS[row[0]]["minor_forte2"] == "crit_rate" else 1)
    logger.info(f'build was: {build}; bonus stats array:')
    logger.info(bonus_stats_dict)

    return {
        "name": row[0],
        "resonance_chain": row[1],
        "weapon": row[2],
        "weapon_rank": row[3],
        "echo": row[4],
        "attack": CHAR_CONSTANTS[row[0]]["base_attack"] * WEAPON_MULTIPLIERS[level_cap][0],
        "health": CHAR_CONSTANTS[row[0]]["base_health"] * WEAPON_MULTIPLIERS[level_cap][0],
        "defense": CHAR_CONSTANTS[row[0]]["base_def"] * WEAPON_MULTIPLIERS[level_cap][0],
        "crit_rate": crit_rate_base,
        "crit_dmg": crit_dmg_base,
        "bonus_stats": bonus_stats_dict,
        "d_cond": {
            'forte': 0,
            'concerto': 0,
            'resonance': 200 if start_full_reso else 0
        }
    }

def pad_and_insert_rows(rows, pos, insert_value, total_columns, is_echo=False):
    for row in rows:
        if is_echo:
            row.insert(pos, None)
        row.insert(pos, insert_value)
        # Pad the row with None values if it's too short
        if len(row) < total_columns:
            row.extend([None] * (total_columns - len(row)))
    return rows

def simulate_active_char_sheet(characters):
    config = load_config(CONFIG_PATH)
    character_tables = config["characters"]["tables"]

    for table in character_tables:
        if table["table_name"] == "Skills":
            skill_table = table
            break

    if not skill_table:
        raise ValueError("Skills table not found in the configuration.")

    db_columns = skill_table["db_columns"]
    total_columns = len(db_columns.keys()) + 1

    forte_pos = list(db_columns.keys()).index("Forte")
    items = list(db_columns.items())
    items.insert(forte_pos, ("Character", "TEXT"))
    db_columns = dict(items)

    table_data = []
    for character in characters:
        intro = fetch_data_from_database(f"{CHARACTERS_DB_PATH}/{character}.db", "Intro")
        outro = fetch_data_from_database(f"{CHARACTERS_DB_PATH}/{character}.db", "Outro")
        echo = fetch_data_comparing_two_databases(
            CONSTANTS_DB_PATH, "Echoes", 
            CALCULATOR_DB_PATH, "CharacterLineup", 
            columns1=["Echo", "DMGPercent", "Time", "EchoSet", "Modifier", "Hits", "Concerto", "Resonance"], columns2="", 
            where_clause=f"t2.Character = '{character}' AND t1.Echo LIKE t2.Echo || '%'")
        skills = fetch_data_from_database(f"{CHARACTERS_DB_PATH}/{character}.db", "Skills")
        
        intro = [list(row) for row in intro]
        outro = [list(row) for row in outro]
        echo = [list(row) for row in echo]
        skills = [list(row) for row in skills]
        
        intro = pad_and_insert_rows(intro, forte_pos, character, total_columns)
        outro = pad_and_insert_rows(outro, forte_pos, character, total_columns)
        echo = pad_and_insert_rows(echo, forte_pos, character, total_columns, is_echo=True)
        skills = pad_and_insert_rows(skills, forte_pos, character, total_columns)

        table_data.extend(intro + outro + echo + skills)

    overwrite_table_data(CALCULATOR_DB_PATH, "ActiveChar", db_columns, table_data)

# Turns a row from "ActiveChar" - aka, the skill data -into a skill data dict.
def row_to_active_skill_object(row):
    concerto = row[8] or 0
    if row[0].startswith("Outro"):
        concerto = -100
    return {
        "name": row[0], # + " (" + row[6] +")",
        "type": "",
        "damage": row[1],
        "cast_time": row[2],
        "dps": row[3],
        "classifications": row[4],
        "number_of_hits": row[5],
        "source": row[6], # the name of the character this skill belongs to
        "d_cond": {
            "forte", row[7] or 0,
            "concerto", concerto,
            "resonance", row[9] or 0
        },
        "freeze_time": row[10] or 0,
        "cooldown": row[11] or 0,
        "max_charges": row[12] or 1
    }

# Loads skills from the calculator "ActiveChar" sheet.
def get_skills():
    values = fetch_data_from_database(CALCULATOR_DB_PATH, "ActiveChar")

    # filter rows where the first cell is not empty
    filtered_values = [row for row in values if row[0].strip() != ""] # Ensure that the name is not empty

    return [row_to_active_skill_object(row) for row in filtered_values]

# The main method that runs all the calculations and updates the data.
# Yes, I know, it's like an 800 line method, so ugly.

def run_calculations():
    character1, character2, character3 = fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", columns="Character")
    old_damage = fetch_data_from_database(CALCULATOR_DB_PATH, "TotalDamage", columns="TotalDamage")[0]
    start_full_reso = fetch_data_from_database(CALCULATOR_DB_PATH, "Settings", columns="TOABoolean")[0] == "TRUE"
    active_buffs = {}
    write_buffs_personal = []
    write_buffs_team = []
    write_stats = []
    write_resonance = []
    write_concerto = []
    write_damage = []
    write_damage_note = []
    characters = [character1, character2, character3]
    simulate_active_char_sheet(characters)
    active_buffs["team"] = set()
    active_buffs[character1] = set()
    active_buffs[character2] = set()
    active_buffs[character3] = set()

    last_seen = {}
    overwrite_table_data_by_row_ids(CALCULATOR_DB_PATH, "TotalDamage", [{"ID": 1, "PreviousTotal": old_damage}])

    initial_d_cond = {}
    cooldown_map = {}

    char_data = {}

    bonus_stats = get_bonus_stats(character1, character2, character3)
    
    for character in characters:
        damage_by_character[character] = 0
        char_entries[character] = 0
        char_stat_gains[character] = {
            "attack": 0,
            "health": 0,
            "defense": 0,
            "crit_rate": 0,
            "crit_dmg": 0,
            "normal": 0,
            "heavy": 0,
            "skill": 0,
            "liberation": 0,
            "flat_attack": 0
        }
    # logger.info(char_stat_gains)
    
    global weapon_data
    weapon_data = {}
    weapons = get_weapons()
    
    characters_weapons_range, weapon_rank_range = zip(*fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", columns=["Weapon", "Rank"]))

    # load echo data into the echo parameter
    echoes = get_echoes()

    for i in range(len(characters)):
        weapon_data[characters[i]] = character_weapon(weapons[characters_weapons_range[i]], level_cap, weapon_rank_range[i])
        row = fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", where_clause=f"ID = {i + 1}")[0]
        char_data[characters[i]] = row_to_character_info(row, level_cap)
        sequences[characters[i]] = char_data[characters[i]]["resonance_chain"]

        echo_name = char_data[characters[i]]["echo"]
        char_data[characters[i]]["echo"] = echoes[echo_name]
        global skill_data
        skill_data[echo_name] = char_data[characters[i]]["echo"]
        logger.info(f'setting skill data for echo {echo_name}; echo cd is {char_data[characters[i]]["echo"]["cooldown"]}')
        initial_d_cond[characters[i]] = {
            "forte": 0,
            "concerto": 0,
            "resonance": 0
        }
        last_seen[characters[i]] = -1

    skill_data = {}
    effect_objects = get_skills()
    for effect in effect_objects:
        skill_data[effect["name"]] = effect

run_calculations()