import logging
import sys
from copy import deepcopy
from functools import cmp_to_key
from utils.database_io import fetch_data_comparing_two_databases, fetch_data_from_database, clear_and_initialize_table, overwrite_table_data, overwrite_table_data_by_row_ids, set_unspecified_columns_to_null
from utils.config_io import load_config
from config.constants import logger, CALCULATOR_DB_PATH, CONFIG_PATH, CONSTANTS_DB_PATH, CHARACTERS_DB_PATH
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from calc_gui import UI

logger = logging.getLogger(__name__)

# Unsilence the silent crashes
sys._excepthook = sys.excepthook 
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback) 
    sys.exit(1) 
sys.excepthook = exception_hook 

# Initialize the App
app = QApplication(sys.argv)
UIWindow = UI()

CHECK_STATS = True

STANDARD_BUFF_TYPES = ["Normal", "Heavy", "Skill", "Liberation"]
ELEMENTAL_BUFF_TYPES = ["Glacio", "Fusion", "Electro", "Aero", "Spectro", "Havoc"]

def initialize_calc_tables():
    """
    Initialize database tables based on configuration settings.

    This function loads the configuration from a JSON file and initializes each table
    specified in the configuration. For each table, it will create the table if it does
    not already exist and optionally insert initial data if provided.

    :raises FileNotFoundError: If the configuration file is not found at the specified path.
    :raises KeyError: If the database name is not found in the configuration file.
    :raises Exception: If there is an issue with loading the configuration or initializing tables.
    """
    config = load_config(CONFIG_PATH)
    tables = config.get(CALCULATOR_DB_PATH)["tables"]
    for table in tables:
        clear_and_initialize_table(CALCULATOR_DB_PATH, table["table_name"], table["db_columns"], initial_data=table.get("initial_data", None))
    logger.info("Calculator database initialized successfully.")
    UIWindow.load_all_table_widgets()

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
last_total_buff_map = {} # the last updated total buff maps for each character
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
        )[0]

try:
    skill_level_multiplier = get_skill_level_multiplier()
except IndexError: # This usually means the calculator database has not been initialized yet
    initialize_calc_tables()
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
    "Attack": 0.086,
    "Health": 0.086,
    "Defense": 0.109,
    "Crit": 0.081,
    "Crit Dmg": 0.162,
    "Normal": 0.086,
    "Heavy": 0.086,
    "Skill": 0.086,
    "Liberation": 0.086,
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
        "duration": row[5] if row[5] == "Passive" else float(row[5]), # How long the buff lasts - a duration is 0 indicates a passive
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
    If the rank is out of bounds, it returns the last value in the string as a float. If the input string is not slash-delimited, 
    it returns the value as a string if it is 'Passive' and as a float otherwise.

    :param value_str: The slash-delimited string containing values.
    :type value_str: str
    :param rank: The rank for which the value is to be extracted.
    :type rank: int
    :return: The extracted value as a float or string.
    :rtype: float or string
    """
    if "/" in value_str:
        values = value_str.split('/')
        return float(values[rank]) if rank < len(values) else float(values[-1])
    elif value_str == "Passive":
        return value_str
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
        "buff_type": weapon_buff["buff_type"], # the type of buff - standard, ATK buff, crit buff, deepen, etc
        "amount": new_amount, # slash delimited - the value of the buff
        "active": True,
        "duration": "Passive" if weapon_buff["duration"] in ("Passive", "0", 0) else new_duration, # slash delimited - how long the buff lasts - a duration is 0 indicates a passive
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

def pad_and_insert_rows(rows, total_columns=None, pos=None, insert_value=None, is_echo=False):
    for row in rows:
        # If is_echo is True and pos is provided, insert None at the specified position
        if is_echo and pos is not None:
            row.insert(pos, None)
        # If pos and insert_value are provided, insert insert_value at the specified position
        if pos is not None and insert_value is not None:
            row.insert(pos, insert_value)
        # Pad the row with None values if it's too short
        if total_columns is not None and len(row) < total_columns:
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
        
        intro = pad_and_insert_rows(intro, total_columns=total_columns, pos=forte_pos, insert_value=character)
        outro = pad_and_insert_rows(outro, total_columns=total_columns, pos=forte_pos, insert_value=character)
        echo = pad_and_insert_rows(echo, total_columns=total_columns, pos=forte_pos, insert_value=character, is_echo=True)
        skills = pad_and_insert_rows(skills, total_columns=total_columns, pos=forte_pos, insert_value=character)

        table_data.extend(intro + outro + echo + skills)

    overwrite_table_data(CALCULATOR_DB_PATH, "ActiveChar", db_columns, table_data)

def simulate_active_effects_sheet(characters):
    config = load_config(CONFIG_PATH)
    character_tables = config["characters"]["tables"]

    for table in character_tables:
        if table["table_name"] == "InherentSkills":
            inherent_skill_table = table
            break

    if not inherent_skill_table:
        raise ValueError("InherentSkills table not found in the configuration.")

    db_columns = inherent_skill_table["db_columns"]
    total_columns = len(db_columns.keys())

    table_data = []
    for character in characters:
        inherent_skills = fetch_data_from_database(f"{CHARACTERS_DB_PATH}/{character}.db", "InherentSkills", where_clause="(Type LIKE '%Buff%' OR Type LIKE '%Dmg%' OR Type LIKE '%Debuff%') AND ActiveBoolean != 'FALSE' AND InherentSkill IS NOT NULL")
        inherent_skills = [list(row) for row in inherent_skills]
        inherent_skills = pad_and_insert_rows(inherent_skills, total_columns=total_columns)
        table_data.extend(inherent_skills)

    overwrite_table_data(CALCULATOR_DB_PATH, "ActiveEffects", db_columns, table_data)

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

"""
Converts a row from the ActiveEffects sheet into a dict. (Buff dict)
@param {Array} row A single row of data from the ActiveEffects sheet.
@return {dict} The row data as an dict.
"""
def row_to_active_effect_object(row):
    is_regular_format = row[7] and str(row[7]).strip() != ""
    activator = row[10] if is_regular_format else row[6]
    global skill_data
    if skill_data.get(row[0]) is not None:
        activator = skill_data[row[0]]["source"]
    if is_regular_format:
        triggered_by_parsed = row[7]
        parsed_condition = None
        parsed_condition2 = None
        if "&" in row[7]:
            triggered_by_parsed = row[7].split("&")[0]
            parsed_condition2 = row[7].split("&")[1]
            logger.info(f'conditions for {row[0]}; {triggered_by_parsed}, {parsed_condition2}')
        elif row[1] != "Dmg" and ";" in row[7]:
            triggered_by_parsed = row[7].split(";")[0]
            parsed_condition = row[7].split(";")[1]
            logger.info(f'{row[0]}; found special condition: {parsed_condition}')
        return {
            "name": row[0], # skill name
            "type": row[1], # The type of buff 
            "classifications": row[2], # The classifications this buff applies to, or All if it applies to all.
            "buff_type": row[3], # The type of buff - standard, ATK buff, crit buff, elemental buff, etc
            "amount": row[4], # The value of the buff
            "duration": row[5] if row[5] == "Passive" else float(row[5]), # How long the buff lasts - a duration is 0 indicates a passive
            "active": row[6], # Should always be TRUE
            "triggered_by": triggered_by_parsed, # The Skill, or Classification type, this buff is triggered by.
            "stack_limit": row[8] or 0, # The maximum stack limit of this buff.
            "stack_interval": row[9] or 0, # The minimum stack interval of gaining a new stack of this buff.
            "applies_to": row[10], # The character this buff applies to, or Team in the case of a team buff
            "can_activate": activator,
            "available_in": 0, # cooltime tracker for proc-based effects
            "special_condition": parsed_condition,
            "additional_condition": parsed_condition2,
            "d_cond": {
                "forte": row[11] or 0,
                "concerto": row[12] or 0,
                "resonance": row[13] or 0
            }
        }
    return { # short format for outros and similar
        "name": row[0],
        "type": row[1],
        "classifications": row[2],
        "buff_type": row[3],
        "amount": row[4],
        "duration": row[5] if row[5] == "Passive" else float(row[5]),
        # Assuming that for these rows, the 'active' field is not present, thus it should be assumed true
        "active": True,
        "triggered_by": "", # No triggered_by field for this format
        "stack_limit": 0, # Assuming 0 as default value if not present
        "stack_interval": 0, # Assuming 0 as default value if not present
        "applies_to": row[6],
        "can_activate": activator,
        "available_in": 0, # cooltime tracker for proc-based effects
        "special_condition": None,
        "additional_condition": None,
        "d_cond": {
            "forte": 0,
            "concerto": 0,
            "resonance": 0
        }
    }

# Loads skills from the calculator "ActiveChar" sheet.
def get_skills():
    values = fetch_data_from_database(CALCULATOR_DB_PATH, "ActiveChar")

    # filter rows where the first cell is not empty
    filtered_values = [row for row in values if row[0].strip() != ""] # Ensure that the name is not empty

    return [row_to_active_skill_object(row) for row in filtered_values]

def get_active_effects():
    values = fetch_data_from_database(CALCULATOR_DB_PATH, "ActiveEffects")
    return [row_to_active_effect_object(row) for row in values if row_to_active_effect_object(row) is not None]

# Buff sorting - damage effects need to always be defined first so if other buffs exist that can be procced by them, then they can be added to the "proccable" list.
# Buffs that have "Buff:" conditions need to be last, as they evaluate the presence of buffs.
def compare_buffs(a, b):
    # If a.type is "Dmg" and b.type is not, a comes first
    if (a["type"] == "Dmg" or "Hl" in a["classifications"]) and (b["type"] != "Dmg" and "Hl" not in b["classifications"]):
        return -1
    # If b.type is "Dmg" and a.type is not, b comes first
    elif (a["type"] != "Dmg" and "Hl" not in a["classifications"]) and (b["type"] == "Dmg" or "Hl" in b["classifications"]):
        return 1
    # If a.triggered_by contains "Buff:" and b does not, b comes first
    elif "Buff:" in a["triggered_by"] and "Buff:" not in b["triggered_by"]:
        return 1
    # If b.triggered_by contains "Buff:" and a does not, a comes first
    elif "Buff:" not in a["triggered_by"] and "Buff:" in b["triggered_by"]:
        return -1
    # Both have the same type or either both are "Dmg" types, or both have the same trigger condition
    # Retain their relative positions
    else:
        return 0

# Extracts the skill reference from the skillData object provided, with the name of the current character.
# Skill data objects have a (Character) name at the end of them to avoid duplicates. Jk, now they don't, but all names MUST be unique.
def get_skill_reference(skill_data, name, character):
    return skill_data[name] # + " (" + character + ")"

def filter_active_buffs(active_buff, swapped, current_time, buffs_to_remove):
    logger.info(f'{active_buff["buff"]["duration"] = }')
    end_time = (
        active_buff["stack_time"] if active_buff["buff"]["type"] == "StackingBuff" 
        else active_buff["start_time"]
    ) + active_buff["buff"]["duration"]
    if active_buff["buff"]["type"] == "BuffUntilSwap" and swapped:
        logger.info(f'BuffUntilSwap buff {active_buff["buff"]["name"]} was removed')
        return False
    if current_time > end_time and active_buff["buff"]["name"] == "Outro: Temporal Bender":
        global jinhsi_outro_active
        jinhsi_outro_active = False
    if current_time > end_time and active_buff["buff"]["type"] == "ResetBuff":
        logger.info(f'resetbuff has triggered: searching for {active_buff["buff"]["classifications"]} to delete')
        buffs_to_remove.append(active_buff["buff"]["classifications"])
    if current_time > end_time:
        logger.info(f'buff {active_buff["buff"]["name"]} has expired; current_time={current_time}; end_time={end_time}')
    return current_time <= end_time  # Keep the buff if the current time is less than or equal to the end time

def filter_team_buffs(active_buff, current_time):
    end_time = (
        active_buff["stack_time"] if active_buff["buff"]["type"] == "StackingBuff" else active_buff["start_time"]
    ) + active_buff["buff"]["duration"]
    return current_time <= end_time  # Keep the buff if the current time is less than or equal to the end time

CLASSIFICATIONS = {
    "No": "normal",
    "He": "heavy",
    "Sk": "skill",
    "Rl": "liberation",
    "Gl": "glacio",
    "Fu": "fusion",
    "El": "electro",
    "Ae": "aero",
    "Sp": "spectro",
    "Ha": "havoc",
    "Ph": "physical",
    "Ec": "echo",
    "Ou": "outro",
    "In": "intro"
}

REVERSE_CLASSIFICATIONS = {value: key for key, value in CLASSIFICATIONS.items()}

def translate_classification_code(code):
    return CLASSIFICATIONS[code] or code # Default to code if not found

def reverse_translate_classification_code(code):
    return REVERSE_CLASSIFICATIONS[code] or code # Default to code if not found

# Handles resonance energy sharing between the party for the given skillRef and value.
def handle_energy_share(value, active_character):
    global characters, weapon_data, bonus_stats, char_data
    for character in characters: # energy share
        # Determine main stat amount if it is "Energy Regen"
        main_stat_amount = (
            weapon_data[character]["main_stat_amount"] if weapon_data[character]["main_stat"] == "Energy Regen" else 0
        )
        # Get the energy recharge from bonus stats
        bonus_energy_recharge = bonus_stats[character]["energyRecharge"]
        # Find the additional energy recharge from character data's bonus stats
        additional_energy_recharge = next(
            (amount for stat, amount in char_data[character]["bonusStats"] if stat == "Energy Regen"), 0
        )
        # Calculate the total energy recharge
        energy_recharge = main_stat_amount + bonus_energy_recharge + additional_energy_recharge
        logger.info(f'adding resonance energy to {character}; current: {char_data[character]["d_cond"]["resonance"]}; value = {value}; energyRecharge = {energy_recharge}; active multiplier: {(1 if character == active_character else 0.5)}')
        char_data[character]["d_cond"]["resonance"] = char_data[character]["d_cond"]["resonance"] + value * (1 + energy_recharge) * (1 if character == active_character else 0.5)

def get_damage_multiplier(classification, total_buff_map):
    global level_cap, enemy_level, res
    damage_multiplier = 1
    damage_bonus = 1
    damage_deepen = 0
    enemy_defense = 792 + 8 * enemy_level
    def_pen = total_buff_map["ignore_defense"]
    defense_multiplier = (800 + level_cap * 8) / (enemy_defense * (1 - def_pen) + 800 + level_cap * 8)
    res_shred = total_buff_map["resistance"]
    # loop through each pair of characters in the classification string
    for i in range(0, len(classification), 2):
        code = classification[i:i + 2]
        classification_name = translate_classification_code(code)
        # if classification is in the total_buff_map, apply its buff amount to the damage multiplier
        if classification_name in total_buff_map:
            if classification_name in STANDARD_BUFF_TYPES: # check for deepen effects as well
                deepen_name = f'{classification_name}_(deepen)'
                if deepen_name in total_buff_map:
                    damage_deepen += total_buff_map[deepen_name]
            damage_bonus += total_buff_map[classification_name]
    res_multiplier = 1
    if res <= 0: # resistance multiplier calculation
        res_multiplier = 1 - (res - res_shred) / 2
    elif res < .8:
        res_multiplier = 1 - (res - res_shred)
    else:
        res_multiplier = 1 / (1 + (res - res_shred) * 5)
    damage_deepen += total_buff_map["deepen"]
    damage_bonus += total_buff_map["specific"]
    logger.info(f'damage multiplier: (BONUS={damage_bonus}) * (MULTIPLIER=1 + {total_buff_map["multiplier"]}) * (DEEPEN=1 + {damage_deepen}) * (RES={res_multiplier}) * (DEF={defense_multiplier})')
    return damage_multiplier * damage_bonus * (1 + total_buff_map["multiplier"]) * (1 + damage_deepen) * res_multiplier * defense_multiplier

# Updates the damage values in the substat estimator as well as the total damage distribution.
# Has an additional 'damage_mult_extra' field for any additional multipliers added on by... hardcoding.
def update_damage(name, classifications, active_character, damage, total_damage, total_buff_map, damage_mult_extra):
    global opener_damage, loop_damage, char_entries, damage_by_character, mode, stat_check_map, char_data, weapon_data, bonus_stats, char_stat_gains, total_damage_map
    char_entries[active_character] += 1
    damage_by_character[active_character] += total_damage
    if mode == "Opener":
        opener_damage += total_damage
    else:
        loop_damage += total_damage
    for stat, value in stat_check_map.items():
        if total_damage > 0:
            current_amount = total_buff_map[stat]
            total_buff_map[stat] = current_amount + value
            attack = (char_data[active_character]["attack"] + weapon_data[active_character]["attack"]) * (1 + total_buff_map["attack"] + bonus_stats[active_character]["attack"]) + total_buff_map["flat_attack"]
            health = (char_data[active_character]["health"]) * (1 + total_buff_map["health"] + bonus_stats[active_character]["health"]) + total_buff_map["flat_health"]
            defense = (char_data[active_character]["defense"]) * (1 + total_buff_map["Defense"] + bonus_stats[active_character]["defense"]) + total_buff_map["flat_defense"]
            crit_multiplier = (1 - min(1, (char_data[active_character]["crit_rate"] + total_buff_map["crit_rate"]))) * 1 + min(1, (char_data[active_character]["crit_rate"] + total_buff_map["crit_rate"])) * (char_data[active_character]["crit_dmg"] + total_buff_map["crit_dmg"])
            damage_multiplier = get_damage_multiplier(classifications, total_buff_map) + (damage_mult_extra or 0)
            scale_factor = defense if "Df" in classifications else (health if "Hp" in classifications else attack)
            new_total_damage = damage * scale_factor * crit_multiplier * damage_multiplier * (0 if weapon_data[active_character]["weapon"]["name"] == "Nullify Damage" else 1)
            char_stat_gains[active_character][stat] += new_total_damage - total_damage
            total_buff_map[stat] = current_amount # unset the value after

    # update damage distribution tracking chart
    for j in range(0, len(classifications), 2):
        code = classifications[j:j + 2]
        key = translate_classification_code(code)
        if "Intro" in name:
            key = "Intro"
        if "Outro" in name:
            key = "Outro"
        if key in total_damage_map:
            current_amount = total_damage_map[key]
            total_damage_map[key] = current_amount + total_damage # Update the total amount
            logger.info(f'updating total damage map [{key}] by {total_damage} (total: {current_amount + total_damage})')
        if key in ["Intro", "Outro"]:
            break

def update_damage(name, classifications, active_character, damage, total_damage, total_buff_map):
    update_damage(name, classifications, active_character, damage, total_damage, total_buff_map, 0)

# Creates a passive damage instance that's actively procced by certain attacks.
class PassiveDamage:
    def __init__(self, name, classifications, type, damage, duration, start_time, limit, interval, triggered_by, owner, slot, d_cond):
        self.name = name
        self.classifications = classifications
        self.type = type
        self.damage = damage
        self.duration = duration
        self.start_time = start_time
        self.limit = limit
        self.interval = interval
        self.triggered_by = triggered_by.split(';')[1]
        self.owner = owner
        self.slot = slot
        self.last_proc = -999
        self.num_procs = 0
        self.proc_multiplier = 1
        self.total_damage = 0
        self.total_buff_map = []
        self.proccable_buffs = []
        self.d_cond = d_cond
        self.activated = False # an activation flag for TickOverTime-based effects
        self.remove = False # a flag for if a passive damage instance needs to be removed (e.g. when a new instance is added)

    def add_buff(self, buff):
        logger.info(f'adding {buff["buff"]["name"]} as a proccable buff to {self.name}')
        logger.info(buff)
        self.proccable_buffs.append(buff)

    # Handles and updates the current proc time according to the skill reference info.
    def handle_procs(self, current_time, cast_time, number_of_hits):
        global queued_buffs
        procs = 0
        time_between_hits = cast_time / (number_of_hits - 1 if number_of_hits > 1 else 1)
        logger.info(f'handle_procs called with current_time: {current_time}, cast_time: {cast_time}, number_of_hits: {number_of_hits}; type: {self.type}')
        logger.info(f'last_proc: {self.last_proc}, interval: {self.interval}, time_between_hits: {time_between_hits}')
        self.activated = True
        if self.interval > 0:
            if self.type == "tick_over_time":
                time = self.last_proc if self.last_proc >= 0 else current_time
                while time <= current_time:
                    procs += 1
                    self.last_proc = time
                    logger.info(f'Proc occurred at hitTime: {time}')
                    time += self.interval
            else:
                for hit_index in range(number_of_hits):
                    hit_time = current_time + time_between_hits * hit_index
                    if hit_time - self.last_proc >= self.interval:
                        procs += 1
                        self.last_proc = hit_time
                        logger.info(f'Proc occurred at hitTime: {hit_time}')
        else:
            procs = number_of_hits
        if self.limit > 0:
            procs = min(procs, self.limit - self.num_procs)
        self.num_procs += procs
        self.proc_multiplier = procs
        logger.info(f'Total procs this time: {procs}')
        if procs > 0:
            for buff in self.proccable_buffs:
                buff_object = buff["buff"]
                if buff_object["type"] == "StackingBuff":
                    stacks_to_add = 1
                    stack_mult = 1 + (1 if "Passive" in buff_object["triggered_by"] and buff_object["name"].startswith("Incandescence") else 0)
                    effective_interval = buff_object["stack_interval"]
                    global jinhsi_outro_active
                    if buff_object["name"].startswith("Incandescence") and jinhsi_outro_active:
                        effective_interval = 1
                    if effective_interval < cast_time: # potentially add multiple stacks
                        max_stacks_by_time = (number_of_hits if effective_interval == 0 else cast_time // effective_interval)
                        stacks_to_add = min(max_stacks_by_time, number_of_hits)
                    logger.info(f'stacking buff {buff_object["name"]} is procced; {buff_object["triggered_by"]}; stacks: {buff["stacks"]}; toAdd: {stacks_to_add}; mult: {stack_mult}; target stacks: {min((stacks_to_add * stack_mult), buff_object["stack_limit"])}; interval: {effective_interval}')
                    buff["stacks"] = min(stacks_to_add * stack_mult, buff_object["stack_limit"])
                    buff["stack_time"] = self.last_proc
                buff["start_time"] = self.last_proc
                queued_buffs.append(buff)
        return procs

    def can_remove(self, current_time, remove_buff):
        return (
            self.num_procs >= self.limit > 0
            or current_time - self.start_time > self.duration
            or (remove_buff and remove_buff in self.name)
            or self.remove
        )

    def can_proc(self, current_time, skill_ref):
        logger(f'can it proc? CT: {current_time}; lastProc: {self.last_proc}; interval: {self.interval}')
        return current_time + skill_ref["cast_time"] - self.last_proc >= self.interval - .01

    # Updates the total buff map to the latest local buffs.
    def update_total_buff_map(self):
        global last_total_buff_map
        if last_total_buff_map[self.owner]:
            self.set_total_buff_map(last_total_buff_map[self.owner])
        else:
            logger.info("undefined last_total_buff_map")

    # Sets the total buff map, updating with any skill-specific buffs.
    def set_total_buff_map(self, total_buff_map):
        self.total_buff_map = dict(total_buff_map)

        # these may have been set from the skill proccing it
        self.total_buff_map["specific"] = 0
        self.total_buff_map["deepen"] = 0
        self.total_buff_map["multiplier"] = 0

        for stat, value in self.total_buff_map.items():
            if stat["name"] in stat:
                if "Specific" in stat:
                    current = self.total_buff_map["specific"]
                    self.total_buff_map["specific"] = current + value
                    logger.info(f'updating damage bonus for {self.name} to {current} + {value}')
                elif "Multiplier" in stat:
                    current = self.total_buff_map["multiplier"]
                    self.total_buff_map["multiplier"] = current + value
                    logger.info(f'updating damage multiplier for {self.name} to {current} + {value}')
                elif "Deepen" in stat:
                    element = reverse_translate_classification_code(stat.split("(")[0].trim())
                    if element in self.classifications:
                        current = self.total_buff_map["deepen"]
                        self.total_buff_map["deepen"] = current + value
                        logger.info(f'updating damage Deepen for {self.name} to {current} + {value}')

        # the tech to apply buffs like this to passive damage effects would be a 99% unnecessary loop so i'm hardcoding this (for now) surely it's not more than a case or two
        global sequences
        if "Marcato" in self.name and sequences["Mortefi"] >= 3:
            self.total_buff_map["crit_dmg"] += 0.3

    def check_proc_conditions(self, skill_ref):
        logger.info(f'checking proc conditions with skill: [{self.triggered_by}] vs {skill_ref["name"]}')
        logger.info(skill_ref)
        if not self.triggered_by:
            return False
        if (self.activated and self.type == "TickOverTime") or self.triggered_by == "Any" or (len(self.triggered_by) > 2 and (skill_ref["name"] in self.triggered_by or self.triggered_by in skill_ref["name"])) or (len(self.triggered_by) == 2 and self.triggered_by in skill_ref["classifications"]):
            return True
        triggered_by_conditions = self.triggered_by.split(",")
        for condition in triggered_by_conditions:
            logger.info(f'checking condition: {condition}; skill ref classifications: {skill_ref["classifications"]}; name: {skill_ref["name"]}')
            if (len(condition) == 2 and condition in skill_ref["classifications"]) or (len(condition) > 2 and (condition in skill_ref["name"] or skill_ref["name"] in condition)):
                return True
        logger.info("failed match")
        return False

    # Calculates a proc's damage, and adds it to the total. Also adds any relevant dynamic conditions.
    def calculate_proc(self, active_character):
        global char_data, weapon_data, bonus_stats, rythmic_vibrato, skill_level_multiplier
        if self.d_cond is not None:
            for condition, value in self.d_cond.items():
                if value > 0:
                    logger.info(f'[PASSIVE DAMAGE] evaluating dynamic condition for {self.name}: {condition} x{value}')
                    if condition == "Resonance":
                        handle_energy_share(value, active_character)
                    else:
                        char_data[active_character]["d_cond"][condition] += value

        bonus_attack = 0
        extra_multiplier = 0
        extra_crit_dmg = 0
        if "Marcato" in self.name:
            extra_multiplier += rythmic_vibrato * 0.015

        total_buff_map = self.total_buff_map
        attack = (char_data[self.owner]["attack"] + weapon_data[self.owner]["attack"]) * (1 + total_buff_map["attack"] + bonus_stats[self.owner]["attack"] + bonus_attack) + total_buff_map["flat_attack"]
        health = (char_data[self.owner]["health"]) * (1 + total_buff_map["health"] + bonus_stats[self.owner]["health"]) + total_buff_map["flat_health"]
        defense = (char_data[self.owner]["defense"]) * (1 + total_buff_map["defense"] + bonus_stats[self.owner]["defense"]) + total_buff_map["flat_defense"]
        crit_multiplier = (1 - min(1, (char_data[self.owner]["crit_rate"] + total_buff_map["crit_rate"]))) * 1 + min(1, (char_data[self.owner]["crit_rate"] + total_buff_map["crit_rate"])) * (char_data[self.owner]["crit_dmg"] + total_buff_map["crit_dmg"] + extra_crit_dmg)
        damage_multiplier = get_damage_multiplier(self.classifications, total_buff_map) + extra_multiplier

        additive_value_key = f'{self.name} (Additive)'
        raw_damage = self.damage * (1 if self.name.startswith("Jué") else skill_level_multiplier) + (total_buff_map[additive_value_key] if additive_value_key in total_buff_map else 0)

        scale_factor = defense if "Df" in self.classifications else (health if "Hp" in self.classifications else attack)
        total_damage = raw_damage * scale_factor * crit_multiplier * damage_multiplier * (0 if weapon_data[self.owner]["weapon"]["name"] == "Nullify Damage" else 1)
        logger.info(f'passive proc damage: {raw_damage:.2f}; attack: {(char_data[self.owner]["attack"] + weapon_data[self.owner]["attack"]):.2f} x {(1 + total_buff_map["attack"] + bonus_stats[self.owner]["attack"]):.2f}; crit mult: {crit_multiplier:.2f}; dmg mult: {damage_multiplier:.2f}; total dmg: {total_damage:.2f}')
        self.total_damage += total_damage * self.proc_multiplier
        update_damage(self.name, self.classifications, self.owner, raw_damage * self.proc_multiplier, total_damage * self.proc_multiplier, total_buff_map, extra_multiplier)
        self.proc_multiplier = 1
        return total_damage

    # Returns a note to place on the cell.
    def get_note(self):
        global sequences, skill_level_multiplier
        additive_value_key = f'{self.name} (Additive)'
        if self.limit == 1:
            return f'This skill triggered an additional damage effect: {self.name}, dealing {self.total_damage:.2f} DMG (Base Ratio: {(self.damage * 100):.2f}%  x {skill_level_multiplier:.2f} + {(self.total_buff_map[additive_value_key] * 100 if additive_value_key in self.total_buff_map else 0)}%).'
        if self.type == "TickOverTime":
            if self.name.startswith("Jué"):
                return f'This skill triggered a passive DOT effect: {self.name}, which has ticked {self.num_procs} times for {self.total_damage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% + {(self.total_buff_map[additive_value_key] * 100 if additive_value_key in self.total_buff_map else 0):.2f}%).'
            return f'This skill triggered a passive DOT effect: {self.name}, which has ticked {self.num_procs} times for {self.total_damage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% x {skill_level_multiplier:.2f} + {(self.total_buff_map[additive_value_key] * 100 if additive_value_key in self.total_buff_map else 0):.2f}%).'
        return f'This skill triggered a passive damage effect: {self.name}, which has procced {self.num_procs} times for {self.total_damage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% x {skill_level_multiplier:.2f} + {(self.total_buff_map[additive_value_key] * 100 if additive_value_key in self.total_buff_map else 0):.2f}%).'

def evaluate_d_cond(value, condition, i, active_character, buff_names, skill_ref, initial_d_cond, total_buff_map):
    global char_data
    if value and value != 0:
        if value < 0:
            if active_character == "Jinhsi" and condition == "Concerto" and "Unison" in buff_names:
                UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                    "Skill", i, 
                    note="The Unison condition has covered the Concerto cost for this Outro.", 
                    font_weight=QFont.Bold)
            else:
                if char_data[active_character]["d_cond"][condition] + value < 0: # ILLEGAL INPUT
                    if condition == "Resonance":
                        # Determine main stat amount if it is "Energy Regen"
                        main_stat_amount = (
                            weapon_data[active_character]["main_stat_amount"] if weapon_data[active_character]["main_stat"] == "Energy Regen" else 0
                        )
                        # Get the energy recharge from bonus stats
                        bonus_energy_recharge = bonus_stats[active_character]["energy_recharge"]
                        # Find the additional energy recharge from character data's bonus stats
                        additional_energy_recharge = next(
                            (amount for stat, amount in char_data[active_character]["bonus_stats"] if stat == "Energy Regen"), 0
                        )
                        # Calculate the total energy recharge
                        energy_recharge = main_stat_amount + bonus_energy_recharge + additional_energy_recharge
                        base_energy = char_data[active_character]["d_cond"][condition] / (1 + energy_recharge)
                        required_recharge = ((value * -1) / base_energy - energy_recharge - 1) * 100
                        UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                            "Skill", i, 
                            note=f'Illegal rotation! At this point, you have {char_data[active_character]["d_cond"][condition]:.2f} out of the required {(value * -1)} {condition} (Requires an additional {required_recharge:.1f}% ERR)', 
                            font_color="#FF0000", font_weight=QFont.Bold)
                    else:
                        no_message = False
                        if active_character == "Jiyan" and "Windqueller" in skill_ref["name"]:
                            no_message = True
                        if not no_message:
                            UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                                "Skill", i, 
                                note=f'Illegal rotation! At this point, you have {char_data[active_character]["d_cond"][condition]:.2f} out of the required {(value * -1)} {condition}', 
                                font_color="#FF0000", font_weight=QFont.Bold)
                    initial_d_cond[active_character][condition] = (value * -1) - char_data[active_character]["d_cond"][condition]
                else:
                    UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                        "Skill", i, 
                        note=f'At this point, you have generated {char_data[active_character]["d_cond"][condition]:.2f} out of the required {(value * -1)} {condition}', 
                        font_weight=QFont.Bold)
                if active_character == "Danjin" or skill_ref["name"].startswith("Outro") or skill_ref["name"].startswith("Liberation"):
                    char_data[active_character]["d_cond"][condition] = 0; # consume all
                else:
                    if active_character == "Jiyan" and "Qingloong Mode" in buff_names and "Windqueller" in skill_ref["name"]: # increase skill damage bonus for this action if forte was consumed, but only if ult is NOT active
                        total_buff_map["specific"] += 0.2
                    else: # adjust the dynamic condition as expected
                        char_data[active_character]["d_cond"][condition] = max(0, char_data[active_character]["d_cond"][condition] + value)
        else:
            if not char_data[active_character]["d_cond"][condition]:
                logger.warning("EH? NaN condition " + condition + " for character " + active_character)
                char_data[active_character]["d_cond"][condition] = 0
            if condition == "Resonance":
                handle_energy_share(value, active_character)
            else:
                if condition == "Forte":
                    logger.info(f'maximum forte: {CHAR_CONSTANTS[active_character]["max_forte"]}; current: {min(char_data[active_character]["d_cond"][condition])}; value to add: {value}')
                    char_data[active_character]["d_cond"][condition] = min(char_data[active_character]["d_cond"][condition] + value, CHAR_CONSTANTS[active_character]["max_forte"])
                else:
                    char_data[active_character]["d_cond"][condition] = char_data[active_character]["d_cond"][condition] + value
        logger.info(char_data[active_character])
        logger.info(char_data[active_character]["d_cond"])
        logger.info(f'dynamic condition [{condition}] updated: {char_data[active_character]["d_cond"][condition]} (+{value})')

# The main method that runs all the calculations and updates the data.
# Yes, I know, it's like an 800 line method, so ugly.

def run_calculations():
    global char_data
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
    simulate_active_effects_sheet(characters)
    active_buffs["team"] = []
    active_buffs[character1] = []
    active_buffs[character2] = []
    active_buffs[character3] = []

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
    
    global weapon_data, skill_data
    weapon_data = {}
    weapons = get_weapons()
    
    try:
        characters_weapons_range, weapon_rank_range = zip(*fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", columns=["Weapon", "Rank"]))
    except ValueError:
        logger.warning("Aborting calculation because no characters or weapons have been chosen")
        return

    # load echo data into the echo parameter
    echoes = get_echoes()

    for i in range(len(characters)):
        weapon_data[characters[i]] = character_weapon(weapons[characters_weapons_range[i]], level_cap, weapon_rank_range[i])
        row = fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", where_clause=f"ID = {i + 1}")[0]
        char_data[characters[i]] = row_to_character_info(row, level_cap)
        sequences[characters[i]] = char_data[characters[i]]["resonance_chain"]

        echo_name = char_data[characters[i]]["echo"]
        char_data[characters[i]]["echo"] = echoes[echo_name]
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

    tracked_buffs = [] # Stores the active buffs for each time point.

    # Outro buffs are special, and are saved to be applied to the NEXT character swapped into.
    queued_buffs_for_next = []
    last_character = None

    swapped = False
    all_buffs = get_active_effects() # retrieves all buffs "in play" from the ActiveEffects table.

    weapon_buffs_range = fetch_data_from_database(CONSTANTS_DB_PATH, "WeaponBuffs")
    weapon_buffs_range = [row for row in weapon_buffs_range if row[0].strip() != ""] # Ensure that the name is not empty
    weapon_buff_data = [row_to_weapon_buff_raw_info(row) for row in weapon_buffs_range]

    echo_buffs_range = fetch_data_from_database(CONSTANTS_DB_PATH, "EchoBuffs")
    echo_buffs_range = [row for row in echo_buffs_range if row[0].strip() != ""] # Ensure that the name is not empty
    echo_buff_data = [row_to_echo_buff_info(row) for row in echo_buffs_range]

    for i in range(3): # loop through characters and add buff data if applicable
        for echo_buff in echo_buff_data:
            if (char_data[characters[i]]["echo"]["name"] in echo_buff["name"] or 
            char_data[characters[i]]["echo"]["echo_set"] in echo_buff["name"]):
                new_buff = create_echo_buff(echo_buff, characters[i])
                all_buffs.append(new_buff)
                logger.info(f'adding echo buff {echo_buff["name"]} to {characters[i]}')
                logger.info(new_buff)

        for weapon_buff in weapon_buff_data:
            if weapon_data[characters[i]]["weapon"]["buff"] in weapon_buff["name"]:
                new_buff = row_to_weapon_buff(weapon_buff, weapon_data[characters[i]]["rank"], characters[i])
                logger.info(f'adding weapon buff {new_buff["name"]} to {characters[i]}')
                logger.info(new_buff)
                all_buffs.append(new_buff)

    # apply passive buffs
    for i in range(len(all_buffs) - 1, -1, -1):
        buff = all_buffs[i]
        if buff["triggered_by"] == "Passive" and buff["duration"] == "Passive" and buff.get("special_condition") is None:
            match buff["type"]:
                case "StackingBuff":
                    buff["duration"] = 9999
                    logger.info(f'passive stacking buff {buff["name"]} applies to: {buff["applies_to"]}; stack interval aka starting stacks: {buff["stack_interval"]}')
                    active_buffs[buff["applies_to"]].append(create_active_stacking_buff(buff, 0, min(buff["stack_interval"], buff["stack_limit"])))
                case "Buff":
                    buff["duration"] = 9999
                    logger.info(f'passive buff {buff["name"]} applies to: {buff["applies_to"]}')
                    active_buffs[buff["applies_to"]].append(create_active_buff(buff, 0))
                    logger.info(f'adding passive buff : {buff["name"]} to {buff["applies_to"]}')

                    all_buffs.pop(i) # remove passive buffs from the list afterwards

    all_buffs = sorted(all_buffs, key=cmp_to_key(compare_buffs))

    # clear the content

    UIWindow.find_table_widget_by_name("RotationBuilder").clear_cell_attributes()
    set_unspecified_columns_to_null(CALCULATOR_DB_PATH, "RotationBuilder", ["Character", "Skill", "InGameTime"])
    UIWindow.find_table_widget_by_name("RotationBuilder").update_subsequent_in_game_times(0)

    current_time = 0
    live_time = 0

    try:
        active_characters, skills, times = zip(*fetch_data_from_database(CALCULATOR_DB_PATH, "RotationBuilder", columns=["Character", "Skill", "InGameTime"]))
    except ValueError:
        logger.warning("Aborting calculation because the rotation is empty")
        return

    bonus_time_total = 0

    for i in range(len(skills)):


        swapped = False
        heal_found = False
        remove_buff = None
        remove_buff_instant = []
        passive_damage_queue = []
        passive_damage_queued = None
        active_character = active_characters[i]
        bonus_time_current = 0
        current_time = times[i] + bonus_time_total
        logger.info(f"new rotation line: {i}; character: {active_character}; skill: {skills[i]}; time: {times[i]} + {bonus_time_total}")

        if last_character is not None and active_character != last_character: # a swap was performed
            swapped = True
        current_skill = skills[i] # the current skill
        skill_ref = get_skill_reference(skill_data, current_skill, active_character)
        if swapped and (current_time - last_seen[active_character]) < 1 and not (skill_ref["name"].startswith("Intro") or skill_ref["name"].startswith("Outro")): # add swap-in time
            extra_to_add = 1 - (current_time - last_seen[active_character])
            logger.info(f'adding extra time. current time: {current_time}; lastSeen: {last_seen[active_character]}; skill: {skill_ref["name"]}; time to add: {1 - (current_time - last_seen[active_character])}')
            overwrite_table_data_by_row_ids(CALCULATOR_DB_PATH, "RotationBuilder", [{"ID": i + 1, "TimeDelay": extra_to_add}])
            UIWindow.find_table_widget_by_name("RotationBuilder").update_subsequent_in_game_times(i - 1)
            bonus_time_total += extra_to_add
            bonus_time_current += extra_to_add
        if len(current_skill) == 0:
            break
        last_seen[active_character] = current_time + skill_ref["cast_time"] - skill_ref["freeze_time"]
        classification = skill_ref["classifications"]
        if "Temporal Bender" in skill_ref["name"]:
            jinhsi_outro_active = True; # just for the sake of saving some runtime so we don't have to loop through buffs or passive effects...
        if "Liberation" in skill_ref["name"]: # reset swap-back timers
            for character in characters:
                last_seen[character] = -1

        if skill_ref["cooldown"] > 0:
            skill_name = skill_ref["name"].split(" (")[0]
            max_charges = skill_ref.get("max_charges", 1)
            if skill_name not in cooldown_map:
                cooldown_map[skill_name] = {
                    "next_valid_time": current_time,
                    "charges": max_charges,
                    "last_used_time": current_time
                }
            skill_track = cooldown_map.get(skill_name)
            elapsed = current_time - skill_track["last_used_time"]
            restored_charges = min(
                elapsed // skill_ref["cooldown"],
                max_charges - skill_track["charges"]
            )
            skill_track["charges"] += restored_charges
            if restored_charges > 0:
                skill_track["last_used_time"] += restored_charges * skill_ref["cooldown"]
            skill_track["next_valid_time"] = skill_track["last_used_time"] + skill_ref["cooldown"]
            logger.info(f'{skill_name}: {skill_track["charges"]}, last used: {skill_track["last_used_time"]}; restored: {restored_charges}; next valid: {skill_track["next_valid_time"]}')

            if skill_track["charges"] > 0:
                if skill_track["charges"] == max_charges: # only update the timer when you're at max stacks to start regenerating the charge
                    skill_track["last_used_time"] = current_time
                skill_track["charges"] -= 1
                cooldown_map[skill_name] = skill_track
            else:
                next_valid_time = skill_track["next_valid_time"]
                logger.info(f'not enough charges for skill. next valid time: {next_valid_time}')
                # Handle the case where the skill is on cooldown and there are no available charges
                if next_valid_time - current_time <= 1:
                    # If the skill will be available soon (within 1 second), adjust the rotation timing to account for this delay
                    delay = next_valid_time - current_time
                    overwrite_table_data_by_row_ids(CALCULATOR_DB_PATH, "RotationBuilder", [{"ID": i + 1, "TimeDelay": max(bonus_time_current, delay)}])
                    UIWindow.find_table_widget_by_name("RotationBuilder").update_subsequent_in_game_times(i - 1)
                    UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                        "In-Game Time", i, 
                        note=f"This skill is on cooldown until {next_valid_time:.2f}. A waiting time of {delay:.2f} seconds was added to accommodate.", 
                        font_color="#FF7F50", font_weight=QFont.Bold)
                    bonus_time_total += delay
                else:
                    # If the skill will not be available soon, mark the rotation as illegal
                    UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                        "In-Game Time", i, 
                        note=f"Illegal rotation! This skill is on cooldown until {next_valid_time:.2f}", 
                        font_color="#FF0000", font_weight=QFont.Bold)
                cooldown_map[skill_name] = skill_track

        active_buffs_array = active_buffs[active_character]
        buffs_to_remove = []
        buff_energy_items = []

        active_buffs_array = [buff for buff in active_buffs_array if filter_active_buffs(buff, swapped, current_time, buffs_to_remove)]
        active_buffs[active_character] = active_buffs_array # Convert the array back into a set (doesn't make sense in python)

        for classification in buffs_to_remove:
            active_buffs[active_character] = {
                buff for buff in active_buffs[active_character] if classification not in buff["buff"]["name"]
            }
            active_buffs["team"] = {
                buff for buff in active_buffs["team"] if classification not in buff["buff"]["name"]
            }

        if swapped and len(queued_buffs_for_next) > 0: # add outro skills after the buffuntilswap check is performed
            for queued_buff in queued_buffs_for_next:
                found = False
                outro_copy = deepcopy(queued_buff)
                outro_copy["buff"]["applies_to"] = active_character if outro_copy["buff"]["applies_to"] == "Next" else outro_copy["buff"]["applies_to"]
                active_set = active_buffs["team"] if queued_buff["buff"]["applies_to"] == "Team" else active_buffs[outro_copy["buff"]["applies_to"]]

                for active_buff in active_set: # loop through and look for if the buff already exists
                    if active_buff["buff"]["name"] == outro_copy["buff"]["name"] and active_buff["buff"]["triggered_by"] == outro_copy["buff"]["triggered_by"]:
                        found = True
                        if active_buff["buff"]["type"] == "StackingBuff":
                            effective_interval = active_buff["buff"]["stack_interval"]
                            if active_buff["buff"]["name"].startswith("Incandescence") and jinhsi_outro_active:
                                effective_interval = 1
                            logger.info(f'current_time: {current_time}; active_buff["stack_time"]: {active_buff["stack_time"]}; effective_interval: {effective_interval}')
                            if current_time - active_buff["stack_time"] >= effective_interval:
                                logger.info(f'updating stacks for {active_buff["buff"]["name"]}: new stacks: {outro_copy["stacks"]} + {active_buff["stacks"]}; limit: {active_buff["buff"]["stack_limit"]}')
                                active_buff["stacks"] = min(active_buff["stacks"] + outro_copy["stacks"], active_buff["buff"]["stack_limit"])
                                active_buff["stack_time"] = current_time
                        else:
                            active_buff["start_time"] = current_time
                            logger.info(f'updating start_time of {active_buff["buff"]["name"]} to {current_time}')
                if not found: # add a new buff
                    active_set.append(outro_copy)
                    logger.info(f'adding new buff from queued_buff_for_next: {outro_copy["buff"]["name"]} x{outro_copy["stacks"]}')

                logger.info(f'Added queued_for_next buff [{queued_buff["buff"]["name"]}] from {last_character} to {active_character}')
                logger.info(outro_copy)
            queued_buffs_for_next = []
        last_character = active_character
        global queued_buffs
        if len(queued_buffs) > 0: # add queued buffs procced from passive effects
            for queued_buff in queued_buffs:
                found = False
                copy = deepcopy(queued_buff)
                copy["buff"]["applies_to"] = active_character if (copy["buff"]["applies_to"] == "Next" or copy["buff"]["applies_to"] == "Active") else copy["buff"]["applies_to"]
                active_set = active_buffs["team"] if copy["buff"]["appliesTo"] == "Team" else active_buffs[copy["buff"]["appliesTo"]]

                logger.info(f'Processing queued buff [{queued_buff["buff"]["name"]}]; applies to {copy["buff"]["appliesTo"]}')
                if "ConsumeBuff" in queued_buff["buff"]["type"]: # a queued consumebuff will instantly remove said buffs
                    remove_buff_instant.append(copy["buff"]["classifications"])
                else:
                    for active_buff in active_set: # loop through and look for if the buff already exists
                        if active_buff["buff"]["name"] == copy["buff"]["name"] and active_buff["buff"]["triggered_by"] == copy["buff"]["triggered_by"]:
                            found = True
                            if active_buff["buff"]["type"] == "StackingBuff":
                                effective_interval = active_buff["buff"]["stackInterval"]
                                if active_buff["buff"]["name"].startswith("Incandescence") and jinhsi_outro_active:
                                    effective_interval = 1
                                logger.info(f'current_time: {current_time}; active_buff["stack_time"]: {active_buff["stack_time"]}; effective_interval: {effective_interval}')
                                if current_time - active_buff["stack_time"] >= effective_interval:
                                    active_buff["stack_time"] = copy["start_time"] # we already calculated the start time based on lastProc
                                    logger.info(f'updating stacks for {active_buff["buff"]["name"]}: new stacks: {copy["stacks"]} + {active_buff["stacks"]}; limit: {active_buff["buff"]["stack_limit"]}; time: {active_buff["stack_time"]}')
                                    active_buff["stacks"] = min(active_buff["stacks"] + copy["stacks"], active_buff["buff"]["stack_limit"])
                                    active_buff["stack_time"] = current_time; # this actually is not accurate, will fix later. should move forward on multihits
                            else:
                                # sometimes a passive instance-triggered effect that procced earlier gets processed later. 
                                # to work around this, check which activated effect procced later
                                if copy["start_time"] > active_buff["start_time"]:
                                    active_buff["start_time"] = copy["start_time"]
                                    logger.info(f'updating startTime of {active_buff["buff"]["name"]} to {copy["start_time"]}')
                    if not found: # add a new buff
                        active_set.append(copy)
                        logger.info(f'adding new buff from queue: {copy["buff"]["name"]} x{copy["stacks"]} at {copy["start_time"]}')
            queued_buffs = []

        active_buffs_array_team = active_buffs["team"]

        active_buffs_array_team = [buff for buff in active_buffs_array_team if filter_team_buffs(buff, current_time)]
        active_buffs["Team"] = active_buffs_array_team  # Convert the list back into a set (doesn't make sense in python)

        # check for new buffs triggered at this time and add them to the active list
        for buff in all_buffs:
            active_set = active_buffs["team"] if buff["applies_to"] == "Team" else active_buffs[active_character]
            triggered_by = buff["triggered_by"]
            if ";" in triggered_by: # for cases that have additional conditions, remove them for the initial check
                triggered_by = triggered_by.split(";")[0]
            intro_outro = "Outro" in buff["name"] or "Intro" in buff["name"]
            if len(triggered_by) == 0 and intro_outro:
                triggered_by = buff["name"]
            if triggered_by == "Any":
                triggered_by = skill_ref["name"] # well that's certainly one way to do it
            triggered_by_conditions = triggered_by.split(',')
            is_activated = False
            special_activated = False
            special_condition_value = 0 # if there is a special >= condition, save this condition for potential proc counts later
            if buff.get("special_condition") and "OnCast" not in buff["special_condition"] and (buff["can_activate"] == "Team" or buff["can_activate"] == active_character): # special conditional
                if ">=" in buff["special_condition"]:
                    # Extract the key and the value from the condition
                    key, value = buff["special_condition"].split(">=", 1)

                    # Convert the value from string to number to compare
                    value = float(value)

                    # Check if the property (key) exists in skillRef
                    if key in char_data[active_character]["d_cond"]:
                        # Evaluate the condition
                        is_activated = char_data[active_character]["d_cond"][key] >= value
                        special_condition_value = char_data[active_character][key]
                    else:
                        logger.info(f'condition not found: {buff["special_condition"]} for skill {skill_ref["name"]}')
                elif ":" in buff["special_condition"]:
                    key, value = buff["special_condition"].split(":", 1)
                    if "Buff" in key: # check the presence of a buff
                        is_activated = False
                        for active_buff in active_set: # loop through and look for if the buff already exists
                            if active_buff["buff"]["name"] == value:
                                is_activated = True
                    else:
                        logger.info(f'unhandled colon condition: {buff["special_condition"]} for skill {skill_ref["name"]}')
                else:
                    logger.info(f'unhandled condition: {buff["special_condition"]} for skill {skill_ref["name"]}')
                special_activated = is_activated
            else:
                special_activated = True
            # check if any of the conditions in triggered_by_conditions match
            is_activated = special_activated
            for condition in triggered_by_conditions:
                condition = condition.strip()
                condition_is_skill_name = len(condition) > 2
                extra_condition = True
                if buff.get("additional_condition"):
                    extra_conditions = buff["additional_condition"].split(",")
                    found_extra = False
                    extra_condition = False
                    for additional_condition in extra_conditions:
                        found = additional_condition in skill_ref["classifications"] if len(additional_condition) == 2 else additional_condition in skill_ref["name"]
                        if found:
                            found_extra = True
                    if found_extra:
                        extra_condition = True
                if extra_condition:
                    if "Buff:" in condition: # check for the existence of a buff
                        buff_name = condition.split(":")[1]
                        logger.info(f'checking for the existence of {buff_name} at time {current_time}')
                        buff_array = active_buffs[active_character]
                        buff_array_team = active_buffs["team"]
                        buff_names = [
                            f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
                            if active_buff["buff"]["type"] == "StackingBuff"
                            else active_buff["buff"]["name"]
                            for active_buff in buff_array] # Extract the name from each object
                        buff_names_team = [
                            f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
                            if active_buff["buff"]["type"] == "StackingBuff"
                            else active_buff["buff"]["name"]
                            for active_buff in buff_array_team] # Extract the name from each object
                        buff_names_string = ", ".join(buff_names)
                        buff_names_string_team = ", ".join(buff_names_team)
                        if buff_name in buff_names_string or buff_name in buff_names_string_team:
                            is_activated = special_activated
                            break
                    elif condition_is_skill_name:
                        for passive_damage_queued in passive_damage_queue:
                            logger.info(
                                f'buff: {buff["name"]}; passive damage queued: {passive_damage_queued is not None}, condition: {condition}, '
                                f'name: {passive_damage_queued.name if passive_damage_queued is not None else "none"}, buff["can_activate"]: {buff["can_activate"]}, '
                                f'owner: {passive_damage_queued.owner if passive_damage_queued is not None else "none"}; additional condition: {buff.get("additional_condition")}')
                            if (passive_damage_queued is not None
                                and ((condition in passive_damage_queued.name or passive_damage_queued.name in condition)
                                or (condition == "Passive" and passive_damage_queued.limit != 1
                                and (passive_damage_queued.type != "TickOverTime" and buff["can_activate"] != "Active")))
                                and (buff["can_activate"] == passive_damage_queued.owner or buff["can_activate"] in ["Team", "Active"])):
                                logger.info(f'[skill name] passive damage queued exists - adding new buff {buff["name"]}')
                                passive_damage_queued.add_buff(create_active_stacking_buff(buff, current_time, 1) if buff["type"] == "StackingBuff" else create_active_buff(buff, current_time))
                        # the condition is a skill name, check if it's included in the currentSkill
                        application_check = buff["applies_to"] == active_character or buff["applies_to"] == "Team" or buff["applies_to"] == "Active" or intro_outro or skill_ref["source"] == active_character
                        if condition == "Swap" and "Intro" not in skill_ref["name"] and (skill_ref["cast_time"] == 0 or "(Swap)" in skill_ref["name"]): # this is a swap-out skill
                            if application_check and ((buff["can_activate"] == active_character or buff["can_activate"] == "Team") or (skill_ref["source"] == active_character and intro_outro)):
                                is_activated = special_activated
                                break
                        else:
                            if condition in current_skill and application_check and (buff["can_activate"] == active_character or buff["can_activate"] == "Team" or (skill_ref["source"] == active_character and buff["applies_to"] == "Next")):
                                is_activated = special_activated
                                break
                    else:
                        for passive_damage_queued in passive_damage_queue:
                            if passive_damage_queued is not None and condition in passive_damage_queued.classifications and (buff["can_activate"] == passive_damage_queued.owner or buff["can_activate"] == "Team"):
                                logger.info(f'passive damage queued exists - adding new buff {buff["name"]}')
                                passive_damage_queued.add_buff(create_active_stacking_buff(buff, current_time, 1) if buff["type"] == "StackingBuff" else create_active_buff(buff, current_time))
                        # the condition is a classification code, check against the classification
                        if (condition in classification or (condition == "Hl" and heal_found)) and (buff["can_activate"] == active_character or buff["can_activate"] == "Team"):
                            is_activated = special_activated
                            break
            if buff["name"].startswith("Incandescence") and "Ec" in skill_ref["classifications"]:
                is_activated = False
            if is_activated: # activate this effect
                found = False
                apply_to_current = True
                stacks_to_add = 1
                logger.info(f'{buff["name"]} has been activated by {skill_ref["name"]} at {current_time}; type: {buff["type"]}; applies_to: {buff["applies_to"]}; class: {buff["classifications"]}')
                if "Hl" in buff["classifications"]: # when a heal effect is procced, raise a flag for subsequent proc conditions
                    heal_found = True
                if buff["type"] == "ConsumeBuffInstant": # these buffs are immediately withdrawn before they are calculating
                    remove_buff_instant.append(buff["classifications"])
                elif buff["type"] == "ConsumeBuff":
                    if remove_buff is not None:
                        logger.info("UNEXPECTED double removebuff condition.")
                    remove_buff = buff["classifications"]; # remove this later, after other effects apply
                elif buff["type"] == "ResetBuff":
                    buff_array = list(active_buffs[active_character])
                    buff_array_team = list(active_buffs["Team"])
                    buff_names = [
                        f'{activeBuff["buff"]["name"]} x{active_buff["stacks"]}'
                        if activeBuff["buff"]["type"] == "StackingBuff"
                        else activeBuff["buff"]["name"]
                        for activeBuff in buff_array] # Extract the name from each object
                    buff_names_team = [
                        f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
                        if active_buff["buff"]["type"] == "StackingBuff"
                        else active_buff["buff"]["name"]
                        for active_buff in buff_array_team] # Extract the name from each object
                    buff_names_string = ", ".join(buff_names)
                    buff_names_string_team = ", ".join(buff_names_team)
                    if buff["name"] not in (buff_names_string, buff_names_string_team):
                        logger.info("adding new active resetbuff")
                        active_set.append(create_active_buff(buff, current_time))
                elif buff["type"] == "Dmg": # add a new passive damage instance
                    # queue the passive damage and snapshot the buffs later
                    logger.info(f'adding a new type of passive damage {buff["name"]}')
                    passive_damage_queued = PassiveDamage(buff["name"], buff["classifications"], buff["buff_type"], buff["amount"], buff["duration"], current_time, buff["stack_limit"], buff["stack_interval"], buff["triggered_by"], active_character, i, buff["d_cond"])
                    if buff["buff_type"] == "TickOverTime" and "Inklet" not in buff["name"]:
                        # for DOT effects, procs are only applied at the end of the interval
                        passive_damage_queued.lastProc = current_time
                    passive_damage_queue.append(passive_damage_queued)
                    logger.info(passive_damage_queued)
                elif buff["type"] == "StackingBuff":
                    effective_interval = buff["stack_interval"]
                    if "Incandescence" in buff["name"] and jinhsi_outro_active:
                        effective_interval = 1
                    logger.info(f'effective_interval: {effective_interval}; cast_time: {skill_ref["cast_time"]}; hits: {skill_ref["number_of_hits"]}; freeze_time: {skill_ref["freeze_time"]}')
                    if effective_interval < (skill_ref["cast_time"] - skill_ref["freeze_time"]): # potentially add multiple stacks
                        if effective_interval == 0:
                            max_stacks_by_time = skill_ref["number_of_hits"]
                        else:
                            max_stacks_by_time = (skill_ref["cast_time"] - skill_ref["freeze_time"]) // effective_interval
                        stacks_to_add = min(max_stacks_by_time, skill_ref["number_of_hits"])
                    if buff["special_condition"] and "on_cast" in buff["special_condition"]:
                        stacks_to_add = 1
                    if buff["name"] == "Resolution" and skill_ref["name"].startswith("Intro: Tactical Strike"):
                        stacks_to_add = 15
                    if special_condition_value > 0: # cap the stacks to add based on the special condition value
                        stacks_to_add = min(stacks_to_add, special_condition_value)
                    logger.info(f'{buff["name"]} is a stacking buff (special condition: {buff["special_condition"]}). attempting to add {stacks_to_add} stacks')
                    for active_buff in active_set: # loop through and look for if the buff already exists
                        if active_buff["buff"]["name"] == buff["name"] and active_buff["buff"]["triggered_by"] == buff["triggered_by"]:
                            found = True
                            logger.info(f'current stacks: {active_buff["stacks"]} last stack: {active_buff["stack_time"]}; current time: {current_time}')
                            if current_time - active_buff["stack_time"] >= effective_interval:
                                active_buff["stacks"] = min(active_buff["stacks"] + stacks_to_add, buff["stack_limit"])
                                active_buff["stack_time"] = current_time
                                logger.info("updating stacking buff: " + buff["name"])
                    if not found: # add a new stackable buff
                        active_set.append(create_active_stacking_buff(buff, current_time, min(stacks_to_add, buff["stack_limit"])))
                else:
                    if "Outro" in buff["name"] or buff["applies_to"] == "Next": # outro buffs are special and are saved for the next character
                        queued_buffs_for_next.append(create_active_buff(buff, current_time))
                        logger.info(f'queuing buff for next: {buff["name"]}')
                        apply_to_current = False
                    else:
                        for active_buff in active_set: # loop through and look for if the buff already exists
                            if active_buff["buff"]["name"] == buff["name"]:
                                # if (currentTime >= activeBuff.availableIn): # if the buff is available to refresh, then refresh. BROKEN. FIX THIS LATER. (only applies to jinhsi unison right now which really doesnt change anything if procs more)
                                active_buff["start_time"] = current_time + skill_ref["cast_time"]
                                # else:
                                #     logger.info(f'the buff {buff["name"]} is not available to refresh until {active_buff["available_in"]}; its interval is {active_buff["stack_interval"]}')
                                found = True
                                logger.info(f'updating starttime of {buff["name"]} to {current_time + skill_ref["cast_time"]}')
                        if not found:
                            if buff["type"] != "buff_energy": # buff_energy available_in is updated when it is applied later on
                                buff["available_in"] = current_time + buff["stack_interval"]
                            active_set.append(create_active_buff(buff, current_time + skill_ref["cast_time"]))
                if buff.get("d_cond") is not None:
                    for condition, value in buff["d_cond"].items():
                        try:
                            buff_names
                        except UnboundLocalError:
                            active_buffs_array = active_buffs[active_character]
                            buff_names = [
                                f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
                                if active_buff["buff"]["type"] == "StackingBuff"
                                else active_buff["buff"]["name"]
                                for active_buff in active_buffs_array]
                        try:
                            total_buff_map
                        except UnboundLocalError:
                            total_buff_map = {
                                "attack": 0,
                                "health": 0,
                                "defense": 0,
                                "crit_rate": 0,
                                "crit_dmg": 0,
                                "normal": 0,
                                "heavy": 0,
                                "skill": 0,
                                "liberation": 0,
                                "normal_(deepen)": 0,
                                "heavy_(deepen)": 0,
                                "skill_(deepen)": 0,
                                "liberation_(deepen)": 0,
                                "physical": 0,
                                "glacio": 0,
                                "fusion": 0,
                                "electro": 0,
                                "aero": 0,
                                "spectro": 0,
                                "havoc": 0,
                                "specific": 0,
                                "deepen": 0,
                                "multiplier": 0,
                                "resistance": 0,
                                "ignore_defense": 0,
                                "flat_attack": 0,
                                "flat_health": 0,
                                "flat_defense": 0,
                                "energy_regen": 0
                            }
                        evaluate_d_cond(value * stacks_to_add, condition, i, active_character, buff_names, skill_ref, initial_d_cond, total_buff_map)







    UIWindow.find_table_widget_by_name("RotationBuilder").load_table_data()

UIWindow.initialize_calc_tables_signal.connect(initialize_calc_tables)
UIWindow.run_calculations_signal.connect(run_calculations)

sys.exit(app.exec_())