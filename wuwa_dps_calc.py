"""
Wuthering Waves DPS Calculator
==============================

by @HikariTenshi
original script by @Maygi

This is the main module of this project. This module initializes the calculator database, 
starts the GUI and provides functionality to perform calculations on the database.
"""

import logging
import math
import sys
from copy import deepcopy
from functools import cmp_to_key
from utils.database_io import table_exists, fetch_data_comparing_two_databases, fetch_data_from_database, clear_and_initialize_table, overwrite_table_data, overwrite_table_data_by_columns, overwrite_table_data_by_row_ids, set_unspecified_columns_to_null, append_rows_to_table
from utils.config_io import load_config
from utils.naming_case import camel_to_snake
from utils.expand_list import set_value_at_index, add_to_list
from config.constants import logger, CALCULATOR_DB_PATH, CONFIG_PATH, CONSTANTS_DB_PATH, CHARACTERS_DB_PATH
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from ui.calc_gui import UI

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

# globals
jinhsi_outro_active = False
rythmic_vibrato = 0

STANDARD_BUFF_TYPES = ["normal", "heavy", "skill", "liberation"]
ELEMENTAL_BUFF_TYPES = ["glacio", "fusion", "electro", "aero", "spectro", "havoc"]

def initialize_calc_tables(check_for_existence=False):
    """
    Initialize database tables if necessary, based on configuration settings.

    This function loads the configuration from a JSON file and initializes each table
    specified in the configuration. For each table, it will create the table if it does
    not already exist and insert initial data if provided in the configuration.

    :param check_for_existence: Whether to check for each table if it exists before initializing it. Defaults to False, this will clear the data.
    :type check_for_existence: bool
    :raises FileNotFoundError: If the configuration file is not found at the specified path.
    :raises KeyError: If the database name is not found in the configuration file.
    :raises Exception: If there is an issue with loading the configuration or initializing tables.
    """
    config = load_config(CONFIG_PATH)
    tables = config.get(CALCULATOR_DB_PATH)["tables"]
    for table in tables:
        if not check_for_existence or not table_exists(CALCULATOR_DB_PATH, table["table_name"]):
            clear_and_initialize_table(CALCULATOR_DB_PATH, table["table_name"], table["db_columns"], initial_data=table.get("initial_data", None))
            logger.debug(f'Table {table["table_name"]} initialized successfully')
    UIWindow.load_all_table_widgets()

initialize_calc_tables(check_for_existence=True)

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
        "type": camel_to_snake(row[1]),
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
            "concerto": row[8] or 0,
            "resonance": row[9] or 0
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
        logger.debug(f'conditions for echo buff {row[0]}; {triggered_by_parsed}, {parsed_condition2}')
    return {
        "name": row[0],
        "type": camel_to_snake(row[1]), # The type of buff 
        "classifications": row[2], # The classifications this buff applies to, or All if it applies to all.
        "buff_type": camel_to_snake(row[3]), # The type of buff - standard, ATK buff, crit buff, elemental buff, etc
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
        logger.debug(f'found a special condition for {row[0]}: {parsed_condition}')
    if "&" in triggered_by_parsed:
        split = triggered_by_parsed.split("&")
        triggered_by_parsed = split[0]
        parsed_condition2 = split[1]
        logger.debug(f'conditions for weapon buff {row[0]}; {triggered_by_parsed}, {parsed_condition2}')
    return {
        "name": row[0], # buff  name
        "type": camel_to_snake(row[1]), # the type of buff 
        "classifications": row[2], # the classifications this buff applies to, or All if it applies to all.
        "buff_type": camel_to_snake(row[3]), # the type of buff - standard, ATK buff, crit buff, deepen, etc
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
    if value_str is None:
        return None
    elif "/" in value_str:
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
    logger.debug(f'weapon buff: {weapon_buff}; amount: {weapon_buff["amount"]}')
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
    for i, character in enumerate(characters):
        # Loop through each stat column
        stats = {stats_order[j]: values[i][j] for j in range(len(stats_order))}
        # Assign the stats object to the corresponding character
        bonus_stats[character] = stats

    return bonus_stats

def get_weapons():
    values = fetch_data_from_database(CONSTANTS_DB_PATH, "Weapons")

    return {
        weapon_info["name"]: weapon_info # Use weapon name as the key for lookup
        for row in values[1:] # Skip header row
        if row[0] # Check if the row actually contains a weapon name
        if (weapon_info := row_to_weapon_info(row)) # Process the row
    }

def get_echoes():
    values = fetch_data_from_database(CONSTANTS_DB_PATH, "Echoes")

    return {
        echo_info["name"]: echo_info # Use echo name as the key for lookup
        for row in values[1:] # Skip header row
        if row[0] # Check if the row actually contains an echo name
        if (echo_info := row_to_echo_info(row)) # Process the row
    }

def update_bonus_stats(dict, key, value):
    # Find the index of the element where the first item matches the key
    for index, element in enumerate(dict):
        if element[0] == key:
            # Update the value at the found index
            dict[index][1] += value
            return  # Exit after updating to prevent unnecessary iterations

def row_to_character_info(row, level_cap, weapon_data, start_full_reso):
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
    logger.debug(row)

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
                logger.debug(
                    f'crit rate base: {crit_rate_base_weapon}; crit rate conditional: '
                    f'{crit_rate_conditional}; crit dmg base: {crit_dmg_base_weapon}'
                )
                if (
                    crit_rate_base + crit_rate_base_weapon + crit_rate_conditional
                ) * 2 < (crit_dmg_base + crit_dmg_base_weapon) - 1:
                    crit_rate_base += 0.22
                else:
                    crit_dmg_base += 0.44
    logger.debug(f'minor fortes: {CHAR_CONSTANTS[row[0]]["minor_forte1"]}, {CHAR_CONSTANTS[row[0]]["minor_forte2"]}; level cap: {level_cap}')
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
    logger.debug(f'build was: {build}; bonus stats array:')
    logger.debug(bonus_stats_dict)

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
            "forte": 0,
            "concerto": 0,
            "resonance": 200 if start_full_reso else 0
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
            "forte": row[7] or 0,
            "concerto": concerto,
            "resonance": row[9] or 0
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
def row_to_active_effect_object(row, skill_data):
    is_regular_format = row[7] and str(row[7]).strip() != ""
    activator = row[10] if is_regular_format else row[6]
    if skill_data.get(row[0]) is not None:
        activator = skill_data[row[0]]["source"]
    if is_regular_format:
        triggered_by_parsed = row[7]
        parsed_condition = None
        parsed_condition2 = None
        if "&" in row[7]:
            triggered_by_parsed = row[7].split("&")[0]
            parsed_condition2 = row[7].split("&")[1]
            logger.debug(f'conditions for {row[0]}; {triggered_by_parsed}, {parsed_condition2}')
        elif row[1] != "Dmg" and ";" in row[7]:
            triggered_by_parsed = row[7].split(";")[0]
            parsed_condition = row[7].split(";")[1]
            logger.debug(f'{row[0]}; found special condition: {parsed_condition}')
        return {
            "name": row[0], # skill name
            "type": camel_to_snake(row[1]), # The type of buff 
            "classifications": row[2], # The classifications this buff applies to, or All if it applies to all.
            "buff_type": camel_to_snake(row[3]), # The type of buff - standard, ATK buff, crit buff, elemental buff, etc
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
        "type": camel_to_snake(row[1]),
        "classifications": row[2],
        "buff_type": camel_to_snake(row[3]),
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

def get_active_effects(skill_data):
    values = fetch_data_from_database(CALCULATOR_DB_PATH, "ActiveEffects")
    return [row_to_active_effect_object(row, skill_data) for row in values if row_to_active_effect_object(row, skill_data) is not None]

# Buff sorting - damage effects need to always be defined first so if other buffs exist that can be procced by them, then they can be added to the "proccable" list.
# Buffs that have "Buff:" conditions need to be last, as they evaluate the presence of buffs.
def compare_buffs(a, b):
    # If a.type is "Dmg" and b.type is not, a comes first
    if (a["type"] == "dmg" or "Hl" in a["classifications"]) and (b["type"] != "dmg" and "Hl" not in b["classifications"]):
        return -1
    # If b.type is "Dmg" and a.type is not, b comes first
    elif (a["type"] != "dmg" and "Hl" not in a["classifications"]) and (b["type"] == "dmg" or "Hl" in b["classifications"]):
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
    global jinhsi_outro_active
    end_time = (
        active_buff["stack_time"] if active_buff["buff"]["type"] == "stacking_buff" 
        else active_buff["start_time"]
    ) + active_buff["buff"]["duration"]
    if active_buff["buff"]["type"] == "buff_until_swap" and swapped:
        logger.debug(f'BuffUntilSwap buff {active_buff["buff"]["name"]} was removed')
        return False
    if "Off-Field" in active_buff["buff"]["name"]:
        logger.debug(f'off-field buff {active_buff["buff"]["name"]} was removed')
        return False
    if current_time > end_time and active_buff["buff"]["name"] == "Outro: Temporal Bender":
        jinhsi_outro_active = False
    if current_time > end_time and active_buff["buff"]["type"] == "reset_buff":
        logger.debug(f'resetbuff has triggered: searching for {active_buff["buff"]["classifications"]} to delete')
        buffs_to_remove.append(active_buff["buff"]["classifications"])
    if current_time > end_time:
        logger.debug(f'buff {active_buff["buff"]["name"]} has expired; current_time={current_time}; end_time={end_time}')
    return current_time <= end_time  # Keep the buff if the current time is less than or equal to the end time

def filter_team_buffs(active_buff, current_time):
    end_time = (
        active_buff["stack_time"] if active_buff["buff"]["type"] == "stacking_buff" else active_buff["start_time"]
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
    return CLASSIFICATIONS.get(code) or code # Default to code if not found

def reverse_translate_classification_code(code):
    return REVERSE_CLASSIFICATIONS.get(code) or code # Default to code if not found

# Handles resonance energy sharing between the party for the given skillRef and value.
def handle_energy_share(value, active_character, characters, char_data, weapon_data, bonus_stats):
    for character in characters: # energy share
        # Determine main stat amount if it is "Energy Regen"
        main_stat_amount = (
            weapon_data[character]["main_stat_amount"] if weapon_data[character]["main_stat"] == "Energy Regen" else 0
        )
        # Get the energy recharge from bonus stats
        bonus_energy_recharge = bonus_stats[character]["energy_recharge"]
        # Find the additional energy recharge from character data's bonus stats
        additional_energy_recharge = next(
            (amount for stat, amount in char_data[character]["bonus_stats"] if stat == "Energy Regen"), 0
        )
        # Calculate the total energy recharge
        energy_recharge = main_stat_amount + bonus_energy_recharge + additional_energy_recharge
        logger.debug(f'adding resonance energy to {character}; current: {char_data[character]["d_cond"]["resonance"]}; value = {value}; energy_recharge = {energy_recharge}; active multiplier: {(1 if character == active_character else 0.5)}')
        char_data[character]["d_cond"]["resonance"] = char_data[character]["d_cond"]["resonance"] + value * (1 + energy_recharge) * (1 if character == active_character else 0.5)

def get_damage_multiplier(classification, total_buff_map, level_cap, enemy_level, res):
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
    logger.debug(f'damage multiplier: (BONUS={damage_bonus}) * (MULTIPLIER=1 + {total_buff_map["multiplier"]}) * (DEEPEN=1 + {damage_deepen}) * (RES={res_multiplier}) * (DEF={defense_multiplier})')
    return damage_multiplier * damage_bonus * (1 + total_buff_map["multiplier"]) * (1 + damage_deepen) * res_multiplier * defense_multiplier

# Updates the damage values in the substat estimator as well as the total damage distribution.
# Has an additional 'damage_mult_extra' field for any additional multipliers added on by... hardcoding.
def update_damage(name, classifications, active_character, damage, total_damage, total_buff_map, char_entries, damage_by_character, mode, opener_damage, loop_damage, stat_check_map, char_data, weapon_data, bonus_stats, level_cap, enemy_level, res, char_stat_gains, total_damage_map, damage_mult_extra=0, bonus_attack=0):
    char_entries[active_character] += 1
    damage_by_character[active_character] += total_damage
    if mode == "opener":
        opener_damage += total_damage
    else:
        loop_damage += total_damage
    for stat, value in stat_check_map.items():
        if total_damage > 0:
            current_amount = total_buff_map[stat]
            total_buff_map[stat] = current_amount + value
            attack = (char_data[active_character]["attack"] + weapon_data[active_character]["attack"]) * (1 + total_buff_map["attack"] + bonus_stats[active_character]["attack"] + (bonus_attack or 0)) + total_buff_map["flat_attack"]
            health = (char_data[active_character]["health"]) * (1 + total_buff_map["health"] + bonus_stats[active_character]["health"]) + total_buff_map["flat_health"]
            defense = (char_data[active_character]["defense"]) * (1 + total_buff_map["defense"] + bonus_stats[active_character]["defense"]) + total_buff_map["flat_defense"]
            crit_multiplier = (1 - min(1, (char_data[active_character]["crit_rate"] + total_buff_map["crit_rate"]))) * 1 + min(1, (char_data[active_character]["crit_rate"] + total_buff_map["crit_rate"])) * (char_data[active_character]["crit_dmg"] + total_buff_map["crit_dmg"])
            damage_multiplier = get_damage_multiplier(classifications, total_buff_map, level_cap, enemy_level, res) + (damage_mult_extra or 0)
            scale_factor = defense if "Df" in classifications else (health if "Hp" in classifications else attack)
            new_total_damage = damage * scale_factor * crit_multiplier * damage_multiplier * (0 if weapon_data[active_character]["weapon"]["name"] == "Nullify Damage" else 1)
            char_stat_gains[active_character][stat] += new_total_damage - total_damage
            total_buff_map[stat] = current_amount # unset the value after

    # update damage distribution tracking chart
    for j in range(0, len(classifications), 2):
        code = classifications[j:j + 2]
        key = translate_classification_code(code)
        if "Intro" in name:
            key = "intro"
        if "Outro" in name:
            key = "outro"
        if key in total_damage_map:
            current_amount = total_damage_map[key]
            total_damage_map[key] = current_amount + total_damage # Update the total amount
            logger.debug(f'updating total damage map [{key}] by {total_damage} (total: {current_amount + total_damage})')
        if key in ["intro", "outro"]:
            break

    return opener_damage, loop_damage

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
        self.last_time = 0 # the last time this passive damage checked time

    def __repr__(self):
        return (f"PassiveDamage(name={self.name!r}, classifications={self.classifications!r}, "
                f"type={self.type!r}, damage={self.damage}, duration={self.duration}, "
                f"start_time={self.start_time}, limit={self.limit}, interval={self.interval}, "
                f"triggered_by={self.triggered_by!r}, owner={self.owner!r}, slot={self.slot}, "
                f"last_proc={self.last_proc}, num_procs={self.num_procs}, total_damage={self.total_damage})")

    def add_buff(self, buff):
        logger.debug(f'adding {buff["buff"]["name"]} as a proccable buff to {self.name}')
        logger.debug(buff)
        self.proccable_buffs.append(buff)

    # Handles and updates the current proc time according to the skill reference info.
    def handle_procs(self, current_time, cast_time, number_of_hits, jinhsi_outro_active, queued_buffs):
        self.last_time = current_time
        procs = 0
        time_between_hits = cast_time / (number_of_hits - 1 if number_of_hits > 1 else 1)
        logger.debug(f'handle_procs called with current_time: {current_time}, cast_time: {cast_time}, number_of_hits: {number_of_hits}; type: {self.type}')
        logger.debug(f'last_proc: {self.last_proc}, interval: {self.interval}, time_between_hits: {time_between_hits}')
        self.activated = True
        if self.interval > 0:
            if self.type == "tick_over_time":
                time = self.last_proc if self.last_proc >= 0 else current_time
                while time <= current_time + cast_time:
                    procs += 1
                    self.last_proc = time
                    logger.debug(f'Proc occurred at hitTime: {time}')
                    time += self.interval
            else:
                for hit_index in range(number_of_hits):
                    hit_time = current_time + time_between_hits * hit_index
                    if hit_time - self.last_proc >= self.interval:
                        procs += 1
                        self.last_proc = hit_time
                        logger.debug(f'Proc occurred at hitTime: {hit_time}')
        else:
            procs = number_of_hits
        if self.limit > 0:
            procs = min(procs, self.limit - self.num_procs)
        self.num_procs += procs
        self.proc_multiplier = procs
        logger.debug(f'Total procs this time: {procs}')
        if procs > 0:
            for buff in self.proccable_buffs:
                buff_object = buff["buff"]
                if buff_object["type"] == "stacking_buff":
                    stacks_to_add = 1
                    stack_mult = 1 + (1 if "Passive" in buff_object["triggered_by"] and buff_object["name"].startswith("Incandescence") else 0)
                    effective_interval = buff_object["stack_interval"]
                    if buff_object["name"].startswith("Incandescence") and jinhsi_outro_active:
                        effective_interval = 1
                    if effective_interval < cast_time: # potentially add multiple stacks
                        max_stacks_by_time = (number_of_hits if effective_interval == 0 else cast_time // effective_interval)
                        stacks_to_add = min(max_stacks_by_time, number_of_hits)
                    logger.debug(f'stacking buff {buff_object["name"]} is procced; {buff_object["triggered_by"]}; stacks: {buff["stacks"]}; toAdd: {stacks_to_add}; mult: {stack_mult}; target stacks: {min((stacks_to_add * stack_mult), buff_object["stack_limit"])}; interval: {effective_interval}')
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
        logger.debug(f'can it proc? CT: {current_time}; lastProc: {self.last_proc}; interval: {self.interval}')
        return current_time + skill_ref["cast_time"] - self.last_proc >= self.interval - .01

    # Updates the total buff map to the latest local buffs.
    def update_total_buff_map(self, last_total_buff_map, sequences):
        if last_total_buff_map[self.owner]:
            self.set_total_buff_map(last_total_buff_map[self.owner], sequences)
        else:
            logger.debug("undefined last_total_buff_map")

    # Sets the total buff map, updating with any skill-specific buffs.
    def set_total_buff_map(self, total_buff_map, sequences):
        self.total_buff_map = dict(total_buff_map)

        # these may have been set from the skill proccing it
        self.total_buff_map["specific"] = 0
        self.total_buff_map["deepen"] = 0
        self.total_buff_map["multiplier"] = 0

        for stat, value in self.total_buff_map.items():
            if self.name in stat:
                if "Specific" in stat:
                    current = self.total_buff_map["specific"]
                    self.total_buff_map["specific"] = current + value
                    logger.debug(f'updating damage bonus for {self.name} to {current} + {value}')
                elif "Multiplier" in stat:
                    current = self.total_buff_map["multiplier"]
                    self.total_buff_map["multiplier"] = current + value
                    logger.debug(f'updating damage multiplier for {self.name} to {current} + {value}')
                elif "Deepen" in stat:
                    element = reverse_translate_classification_code(stat.split("(")[0].trim())
                    if element in self.classifications:
                        current = self.total_buff_map["deepen"]
                        self.total_buff_map["deepen"] = current + value
                        logger.debug(f'updating damage Deepen for {self.name} to {current} + {value}')

        # the tech to apply buffs like this to passive damage effects would be a 99% unnecessary loop so i'm hardcoding this (for now) surely it's not more than a case or two
        if "Marcato" in self.name and sequences["Mortefi"] >= 3:
            self.total_buff_map["crit_dmg"] += 0.3

    def check_proc_conditions(self, skill_ref):
        logger.debug(f'checking proc conditions with skill: [{self.triggered_by}] vs {skill_ref["name"]}')
        logger.debug(skill_ref)
        if not self.triggered_by:
            return False
        if (self.activated and self.type == "TickOverTime") or self.triggered_by == "Any" or (len(self.triggered_by) > 2 and (skill_ref["name"] in self.triggered_by or self.triggered_by in skill_ref["name"])) or (len(self.triggered_by) == 2 and self.triggered_by in skill_ref["classifications"]):
            return True
        triggered_by_conditions = self.triggered_by.split(",")
        for condition in triggered_by_conditions:
            logger.debug(f'checking condition: {condition}; skill ref classifications: {skill_ref["classifications"]}; name: {skill_ref["name"]}')
            if (len(condition) == 2 and condition in skill_ref["classifications"]) or (len(condition) > 2 and (condition in skill_ref["name"] or skill_ref["name"] in condition)):
                return True
        logger.debug("failed match")
        return False

    # Calculates a proc's damage, and adds it to the total. Also adds any relevant dynamic conditions.
    def calculate_proc(self, active_character, characters, char_data, weapon_data, bonus_stats, last_seen, rythmic_vibrato, level_cap, enemy_level, res, skill_level_multiplier, opener_damage, loop_damage, char_entries, damage_by_character, mode, stat_check_map, char_stat_gains, total_damage_map):
        if self.d_cond is not None:
            for condition, value in self.d_cond.items():
                if value > 0:
                    logger.debug(f'[PASSIVE DAMAGE] evaluating dynamic condition for {self.name}: {condition} x{value}')
                    if condition == "Resonance":
                        handle_energy_share(value, active_character, characters, char_data, weapon_data, bonus_stats)
                    else:
                        char_data[active_character]["d_cond"][condition] += value

        bonus_attack = 0
        if active_character != self.owner:
            if "Stringmaster" in char_data[self.owner]["weapon"]: # sorry... hardcoding just this once
                if self.last_time - last_seen[self.owner] > 5 or self.owner != "Yinlin":
                    bonus_attack -= (0.12 + weapon_data[self.owner]["rank"] * 0.03) * 2
        extra_multiplier = 0
        extra_crit_dmg = 0
        if "Marcato" in self.name:
            extra_multiplier += rythmic_vibrato * 0.015

        total_buff_map = self.total_buff_map
        attack = (char_data[self.owner]["attack"] + weapon_data[self.owner]["attack"]) * (1 + total_buff_map["attack"] + bonus_stats[self.owner]["attack"] + bonus_attack) + total_buff_map["flat_attack"]
        health = (char_data[self.owner]["health"]) * (1 + total_buff_map["health"] + bonus_stats[self.owner]["health"]) + total_buff_map["flat_health"]
        defense = (char_data[self.owner]["defense"]) * (1 + total_buff_map["defense"] + bonus_stats[self.owner]["defense"]) + total_buff_map["flat_defense"]
        crit_multiplier = (1 - min(1, (char_data[self.owner]["crit_rate"] + total_buff_map["crit_rate"]))) * 1 + min(1, (char_data[self.owner]["crit_rate"] + total_buff_map["crit_rate"])) * (char_data[self.owner]["crit_dmg"] + total_buff_map["crit_dmg"] + extra_crit_dmg)
        damage_multiplier = get_damage_multiplier(self.classifications, total_buff_map, level_cap, enemy_level, res) + extra_multiplier

        additive_value_key = f'{self.name} (Additive)'
        raw_damage = self.damage * (1 if self.name.startswith("Jué") else skill_level_multiplier) + (total_buff_map[additive_value_key] if additive_value_key in total_buff_map else 0)

        scale_factor = defense if "Df" in self.classifications else (health if "Hp" in self.classifications else attack)
        total_damage = raw_damage * scale_factor * crit_multiplier * damage_multiplier * (0 if weapon_data[self.owner]["weapon"]["name"] == "Nullify Damage" else 1)
        logger.debug(f'passive proc damage ({self.name}): {raw_damage:.2f}; attack: {(char_data[self.owner]["attack"] + weapon_data[self.owner]["attack"]):.2f} x {(1 + total_buff_map["attack"] + bonus_stats[self.owner]["attack"] + bonus_attack):.2f}; crit mult: {crit_multiplier:.2f}; dmg mult: {damage_multiplier:.2f}; total dmg: {total_damage:.2f}')
        self.total_damage += total_damage * self.proc_multiplier
        opener_damage, loop_damage = update_damage(
            name=self.name, 
            classifications=self.classifications, 
            active_character=self.owner, 
            damage=(raw_damage * self.proc_multiplier), 
            total_damage=(total_damage * self.proc_multiplier), 
            total_buff_map=total_buff_map, 
            char_entries=char_entries, 
            damage_by_character=damage_by_character, 
            mode=mode, 
            opener_damage=opener_damage, 
            loop_damage=loop_damage, 
            stat_check_map=stat_check_map, 
            char_data=char_data, 
            weapon_data=weapon_data, 
            bonus_stats=bonus_stats, 
            level_cap=level_cap, 
            enemy_level=enemy_level, 
            res=res, 
            char_stat_gains=char_stat_gains, 
            total_damage_map=total_damage_map, 
            damage_mult_extra=extra_multiplier,
            bonus_attack=bonus_attack)
        self.proc_multiplier = 1
        return total_damage

    # Returns a note to place on the cell.
    def get_note(self, skill_level_multiplier):
        additive_value_key = f'{self.name} (Additive)'
        if self.limit == 1:
            return f'This skill triggered an additional damage effect: {self.name}, dealing {self.total_damage:.2f} DMG (Base Ratio: {(self.damage * 100):.2f}%  x {skill_level_multiplier:.2f} + {(self.total_buff_map[additive_value_key] * 100 if additive_value_key in self.total_buff_map else 0)}%).'
        if self.type == "TickOverTime":
            if self.name.startswith("Jué"):
                return f'This skill triggered a passive DOT effect: {self.name}, which has ticked {self.num_procs} times for {self.total_damage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% + {(self.total_buff_map[additive_value_key] * 100 if additive_value_key in self.total_buff_map else 0):.2f}%).'
            return f'This skill triggered a passive DOT effect: {self.name}, which has ticked {self.num_procs} times for {self.total_damage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% x {skill_level_multiplier:.2f} + {(self.total_buff_map[additive_value_key] * 100 if additive_value_key in self.total_buff_map else 0):.2f}%).'
        return f'This skill triggered a passive damage effect: {self.name}, which has procced {self.num_procs} times for {self.total_damage:.2f} DMG in total (Base Ratio: {(self.damage * 100):.2f}% x {skill_level_multiplier:.2f} + {(self.total_buff_map[additive_value_key] * 100 if additive_value_key in self.total_buff_map else 0):.2f}%).'

def evaluate_d_cond(value, condition, i, active_character, characters, char_data, weapon_data, bonus_stats, buff_names, skill_ref, initial_d_cond, total_buff_map):
    if value and value != 0:
        if value < 0:
            if active_character == "Jinhsi" and condition == "Concerto" and "Unison" in buff_names:
                UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                    "Skill", i, 
                    note="The Unison condition has covered the Concerto cost for this Outro.", 
                    font_weight=QFont.Bold)
            else:
                ignore_condition = False
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
                            note=f'Illegal rotation! At this point, you have {char_data[active_character]["d_cond"][condition]:.2f} out of the required {(value * -1)} {condition} (Requires an additional {required_recharge:.1f}% ER)', 
                            font_color="#FF0000", font_weight=QFont.Bold)
                    else:
                        if active_character == "Jiyan" and "Windqueller" in skill_ref["name"] or active_character == "Zhezhi" and "Depiction" in skill_ref["name"]:
                            ignore_condition = True
                        if not ignore_condition:
                            UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                                "Skill", i, 
                                note=f'Illegal rotation! At this point, you have {char_data[active_character]["d_cond"][condition]:.2f} out of the required {(value * -1)} {condition}', 
                                font_color="#FF0000", font_weight=QFont.Bold)
                    if not ignore_condition:
                        logger.debug(f'evaluating dcond for skill {skill_ref["name"]}; updating {condition} by {value * -1}')
                        initial_d_cond[active_character][condition] = (value * -1) - char_data[active_character]["d_cond"][condition]
                else:
                    UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                        "Skill", i, 
                        note=f'At this point, you have generated {char_data[active_character]["d_cond"][condition]:.2f} out of the required {(value * -1)} {condition}', 
                        font_weight=QFont.Bold)
                if not ignore_condition:
                    if active_character == "Danjin" or skill_ref["name"].startswith("Outro") or skill_ref["name"].startswith("Liberation"):
                        char_data[active_character]["d_cond"][condition] = 0; # consume all
                    elif active_character == "Jiyan" and "Qingloong Mode" in buff_names and "Windqueller" in skill_ref["name"]: # increase skill damage bonus for this action if forte was consumed, but only if ult is NOT active
                        total_buff_map["specific"] += 0.2
                    else: # adjust the dynamic condition as expected
                        logger.debug(f'evaluating dcond for skill {skill_ref["name"]}; updating {condition} by {value}')
                        char_data[active_character]["d_cond"][condition] = max(0, char_data[active_character]["d_cond"][condition] + value)
        else:
            if not char_data[active_character]["d_cond"][condition]:
                logger.debug("EH? NaN condition " + condition + " for character " + active_character)
                char_data[active_character]["d_cond"][condition] = 0
            if condition == "Resonance":
                handle_energy_share(value, active_character, characters, char_data, weapon_data, bonus_stats)
            else:
                if condition == "Forte":
                    logger.debug(f'maximum forte: {CHAR_CONSTANTS[active_character]["max_forte"]}; current: {min(char_data[active_character]["d_cond"][condition])}; value to add: {value}')
                    char_data[active_character]["d_cond"][condition] = min(char_data[active_character]["d_cond"][condition] + value, CHAR_CONSTANTS[active_character]["max_forte"])
                else:
                    char_data[active_character]["d_cond"][condition] = char_data[active_character]["d_cond"][condition] + value
        logger.debug(char_data[active_character])
        logger.debug(char_data[active_character]["d_cond"])
        logger.debug(f'dynamic condition [{condition}] updated: {char_data[active_character]["d_cond"][condition]} (+{value})')

def remove_text_within_parentheses(input_string):
    while '(' in input_string and ')' in input_string:
        start = input_string.find('(')
        end = input_string.find(')', start) + 1
        input_string = input_string[:start] + input_string[end:]
    return input_string.strip()

def extract_number_after_x(input_string):
    x_index = input_string.find('x')
    
    if x_index == -1:
        return None

    number_start_index = x_index + 1

    # Check if the character after 'x' is a digit
    if number_start_index < len(input_string) and input_string[number_start_index].isdigit():
        number_end_index = number_start_index

        # Find the end of the digit sequence
        while number_end_index < len(input_string) and input_string[number_end_index].isdigit():
            number_end_index += 1

        return int(input_string[number_start_index:number_end_index])

    return None

"""
Updates the total buff map.
@buff_category - The base type of the buff (All , AllEle, Fu, Sp, etc)
@buff_type - The specific type of the buff (Bonus, Attack, Additive)
@buff_amount - The amount of the buff to add
@buff_max - The maximum buff value for the stack, for particular buffs have multiple different variations contributing to the same cap (e.g. Jinhsi Incandesence)
"""
def update_total_buff_map(buff_category, buff_type, buff_amount, buff_max, total_buff_map, char_data, active_character, skill_ref):
    if buff_category == "All":
        for buff in STANDARD_BUFF_TYPES:
            new_key = translate_classification_code(buff)
            new_key = f'{new_key} ({buff_type})' if buff_type == "Deepen" else f'{new_key}'
            if new_key not in total_buff_map:
                return
            total_buff_map[new_key] += buff_amount # Update the total amount
    elif buff_category == "AllEle":
        for buff in ELEMENTAL_BUFF_TYPES:
            new_key = translate_classification_code(buff)
            if new_key not in total_buff_map:
                return
            total_buff_map[new_key] += buff_amount # Update the total amount
    else:
        categories = buff_category.split(",")
        for category in categories:
            new_key = translate_classification_code(category)
            base_key = remove_text_within_parentheses(new_key)
            new_key = f'{new_key} ({buff_type})' if buff_type == "Deepen" else f'{new_key}'
            additional_condition = None
            if "*" in buff_type: # this is a dynamic buff value that multiplies by a certain condition
                split = buff_type.split("*")
                buff_type = split[0]
                buff_amount *= char_data[active_character]["d_cond"][split[1]]
                logger.debug(f'found multiplicative condition for buff amount: multiplying {buff_amount} by {split[1]} ({char_data[active_character]["d_cond"][split[1]]})')
            if "&" in buff_type: # this is a dual condition buff
                split = buff_type.split("&")
                buff_type = split[0]
                additional_condition = split[1]
                logger.debug(f'found dual condition for buff type: {additional_condition}')
            buff_key = "Specific" if buff_type == "Bonus" else ("Deepen" if buff_type == "Deepen" else "Multiplier")
            if buff_type == "Additive": # an additive value to a skill multiplier
                buff_key = "Additive"
                new_key = f'{base_key} ({buff_key})'
                if new_key in total_buff_map:
                    current_bonus = total_buff_map[new_key]
                    max_value = 99999
                    if buff_max > 0:
                        max_value = buff_max
                    total_buff_map[new_key] = min(max_value, current_bonus + buff_amount) # Update the total amount
                    logger.debug(f'updating {new_key}: {current_bonus} + {buff_amount}, capped at {max_value}')
                else: # add the skill key as a new value for potential procs
                    total_buff_map[new_key] = buff_amount
                    logger.debug(f'no match, but adding additive key {new_key} = {buff_amount}')
            elif buff_key == "Deepen" and base_key not in STANDARD_BUFF_TYPES: # apply element-specific deepen effects IF MATCH
                if (len(category) == 2 and category in skill_ref["classifications"]) or (len(category) > 2 and category in skill_ref["name"]):
                    new_key = "Deepen"
                    logger.debug(f'updating amplify; current {total_buff_map[new_key]} (+{buff_amount})')
                    total_buff_map[new_key] += buff_amount # Update the total amount
            elif buff_type == "Resistance": # apply resistance effects IF MATCH
                if (len(category) == 2 and category in skill_ref["classifications"]) or (len(category) > 2 and category in skill_ref["name"]):
                    new_key = "Resistance"
                    logger.debug(f'updating res shred; current {total_buff_map[new_key]} (+{buff_amount})')
                    total_buff_map[new_key] += buff_amount # Update the total amount
            elif buff_type == "Ignore Defense": # ignore defense IF MATCH
                if (len(category) == 2 and category in skill_ref["classifications"]) or (len(category) > 2 and category in skill_ref["name"]):
                    new_key = "Ignore Defense"
                    logger.debug(f'updating ignore def; current {total_buff_map[new_key]} (+{buff_amount})')
                    total_buff_map[new_key] += buff_amount # Update the total amount
            else:
                if new_key not in total_buff_map: # skill-specific buff
                    if new_key in skill_ref["name"]:
                        current_bonus = total_buff_map[buff_key]
                        total_buff_map[buff_key] = current_bonus + buff_amount # Update the total amount
                        logger.debug(f'updating new key from {new_key}; current bonus: {current_bonus}; buffKey: {buff_key}; buffAmount: {buff_amount}')
                    else: # add the skill key as a new value for potential procs
                        total_buff_map[f'{new_key} ({buff_key})'] = buff_amount
                        logger.debug(f'no match, but adding key {new_key} ({buff_key})')
                else:
                    total_buff_map[new_key] += buff_amount # Update the total amount

# Process buff array
def process_buffs(buffs, current_time, char_data, active_character, total_buff_map, skill_ref):
    global rythmic_vibrato
    for buff_wrapper in buffs:
        buff = buff_wrapper["buff"]
        logger.debug(f'buff: {buff["name"]}; buff_type: {buff["type"]}; current time: {current_time}; available in: {buff["available_in"]}')
        if buff["name"] == "Rythmic Vibrato": # we don't re-poll buffs for passive damage instances currently so it needs to keep track of this lol
            rythmic_vibrato = buff_wrapper["stacks"]

        if buff["type"] == "buff_energy" and current_time >= buff["available_in"]: # add energy instead of adding the buff
            logger.debug(f'adding BuffEnergy dynamic condition: " + {buff["amount"]} + " for type " + {buff["buff_type"]}')
            buff["available_in"] = current_time + buff["stack_interval"]
            char_data[active_character]["d_cond"][buff["buff_type"]] = float(char_data[active_character]["d_cond"][buff["buff_type"]]) + float(buff["amount"]) * max(float(buff_wrapper["stacks"]), 1)
            logger.debug(f'total {buff["buff_type"]} after: {char_data[active_character]["d_cond"][buff["buff_type"]]}')

        nullify = False
        if "Off-Field" in buff["name"] and ("Outro" not in skill_ref["name"] and "Swap" not in skill_ref["name"]):
            nullify = True

        if not nullify:
            # special buff types are handled slightly differently
            special_buff_types = ["Attack", "Health", "Defense", "Crit", "Crit Dmg"]
            if buff["buff_type"] in special_buff_types:
                update_total_buff_map(buff["buff_type"], "", buff["amount"] * (buff_wrapper["stacks"] if buff["type"] == "stacking_buff" else 1), buff["amount"] * buff["stack_limit"], total_buff_map, char_data, active_character, skill_ref)
            else: # for other buffs, just use classifications as is
                update_total_buff_map(buff["classifications"], buff["buff_type"], buff["amount"] * (buff_wrapper["stacks"] if buff["type"] == "stacking_buff" else 1), buff["amount"] * buff["stack_limit"], total_buff_map, char_data, active_character, skill_ref)

def write_buffs_to_sheet(total_buff_map, bonus_stats, char_data, active_character, write_stats):
    values = []
    
    for key in total_buff_map:
        value = total_buff_map[key]
        match(key):
            case "attack":
                value += bonus_stats[active_character]["attack"]
            case "health":
                value += bonus_stats[active_character]["health"]
            case "defense":
                value += bonus_stats[active_character]["defense"]
            case "crit_rate":
                value += char_data[active_character]["crit_rate"]
            case "crit_dmg":
                value += char_data[active_character]["crit_dmg"]
        values.append(value)

    if len(values) > 25:
        values = values[:25]
    write_stats.append(values)

def import_build():
    clipboard = QApplication.clipboard()
    build = clipboard.text()

    if build and len(build) > 0:
        sections = build.split(";")
        if len(sections) != 5:
            logger.error(f'Malformed build. Could not import. Found {len(sections)} sections; expected 5')
        else:
            UIWindow.find_table_widget_by_name("RotationBuilder").clear_cell_attributes()
            config = load_config(CONFIG_PATH)
            calculator_tables = config.get(CALCULATOR_DB_PATH)["tables"]
            
            for table in calculator_tables:
                if table["table_name"] == "RotationBuilder":
                    rotation_builder_table = table
                    break

            if not rotation_builder_table:
                raise ValueError("RotationBuilder table not found in the configuration.")
            
            clear_and_initialize_table(CALCULATOR_DB_PATH, rotation_builder_table["table_name"], rotation_builder_table["db_columns"])
            
            rota_section = sections[4]
            char_sections = ""
            divider = ""
            for i in range(1, 4): # import the 3 character sections
                char_sections += divider
                char_sections += sections[i]
                divider = ";"

            # import the base character details

            rows = char_sections.split(";"); # Split by each character input block

            for row_index, row in enumerate(rows):
                values = row.split(",")

                if len(values) < 29:
                    logger.warning(f'Row {row_index + 1} does not contain the required 29 values.')
                    continue; # Skip this row if it doesn't have enough values

                try:
                    overwrite_table_data_by_row_ids(CALCULATOR_DB_PATH, "CharacterLineup", [{
                        "ID": row_index + 1,
                        "Character": values[0],
                        "ResonanceChain": values[1],
                        "Weapon": values[2],
                        "Rank": values[4],
                        "Echo": values[5],
                        "Build": values[6],
                        "Attack": values[7],
                        "AttackPercent": values[25],
                        "Health": values[8],
                        "HealthPercent": values[26],
                        "Defense": values[9],
                        "DefensePercent": values[27],
                        "CritRate": values[10],
                        "CritDamage": values[11],
                        "EnergyRegen": values[28],
                        "NormalBonus": values[12],
                        "HeavyBonus": values[13],
                        "SkillBonus": values[14],
                        "LiberationBonus": values[15]
                    }])
                except Exception as e:
                    logger.error(f'error in importing build: {e}')

            # import the rotation

            entries = rota_section.split(",")

            # Prepare arrays to hold character names and skills separately
            character_data = []
            skill_data = []

            for entry in entries:
                character, skill = entry.split("&")
                character_data.append(character)
                skill_data.append(skill)

            try:
                overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "RotationBuilder", "Character", character_data)
                overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "RotationBuilder", "Skill", skill_data)
                overwrite_table_data_by_row_ids(CALCULATOR_DB_PATH, "RotationBuilder", [{"ID": 1, "InGameTime": 0.0}])

                UIWindow.find_table_widget_by_name("CharacterLineup").load_table_data()
                UIWindow.find_table_widget_by_name("RotationBuilder").load_table_data()
                UIWindow.find_table_widget_by_name("RotationBuilder").update_subsequent_in_game_times(0)
            except Exception as e:
                logger.error(f'error in importing build: {e}')

# Turns a row into a raw character data info for build exporting.
def row_to_character_info_raw(row):
    return {
        "name": row[1],
        "resonance_chain": row[2],
        "weapon": row[3],
        "weapon_rank": row[5],
        "echo": row[6],
        "build": row[7],
        "attack": row[8],
        "health": row[9],
        "defense": row[10],
        "crit_rate": row[11],
        "crit_dmg": row[12],
        "normal": row[13],
        "heavy": row[14],
        "skill": row[15],
        "liberation": row[16]
    }

"""
Generates the build_string for exporting.
Format:
Friendly Name; CSV Stats & Bonus Stats; Stats 2; Stats 3; CSV Rotation (Format: Character&Skill)

Example:
S1R1 Jinhsi + Ages of Harvest / ... ; 100,0,0,43%,81%,...; [x3] Jinshi&Skill: Test,Jinshi&Basic: Test2
"""
def generate_build_string():
    characters, resonance_chains, weapons, ranks, echoes, builds, attack_values, attack_percent_values, health_values, health_percent_values, defense_values, defense_percent_values, crit_rate_values, crit_damage_values, energy_regen_values, avg_hp_values, normal_bonuses, heavy_bonuses, skill_bonuses, liberation_bonuses = zip(*fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup"))
    empty = ("", "", "")
    zero = (0, 0, 0)
    char_info_raw = tuple(zip(characters, resonance_chains, weapons, empty, ranks, echoes, builds, attack_values, health_values, defense_values, crit_rate_values, crit_damage_values, normal_bonuses, heavy_bonuses, skill_bonuses, liberation_bonuses, zero, zero, zero, zero, zero, zero, zero, empty, empty))
    bonus_stats = tuple(zip(attack_percent_values, health_percent_values, defense_percent_values, energy_regen_values))
    build_string = ""
    divider = ""
    for i, character in enumerate(characters):
        build_string += divider
        build_string += "S"
        build_string += str(resonance_chains[i])
        build_string += "R"
        build_string += str(ranks[i])
        build_string += " "
        build_string += character
        build_string += " + "
        build_string += weapons[i]
        divider = " / "
    build_string += ";"
    divider2 = ""
    for i, _ in enumerate(characters):
        build_string += divider2
        divider = ""
        for char_row in char_info_raw[i]:
            build_string += divider
            build_string += "0" if isinstance(char_row, float) and math.isclose(char_row, 0.0) else str(char_row)
            divider = ","
        for stat in bonus_stats[i]:
            build_string += divider
            build_string += "0" if isinstance(stat, float) and math.isclose(stat, 0.0) else str(stat)
            divider = ","
        divider2 = ";"
    build_string += ";"

    divider = ""
    rotation = fetch_data_from_database(CALCULATOR_DB_PATH, "RotationBuilder", ["Character", "Skill"])
    for character, skill in rotation:
        if not character or not skill:
            break
        build_string += divider
        build_string += character
        build_string += "&"
        build_string += skill
        divider = ","
    return build_string

def export_build():
    clipboard = QApplication.clipboard()
    clipboard.setText(generate_build_string())

# save the previous execution to the first open slot
def save_to_execution_history(characters, build_string):
    opener_dps, loop_dps, dps2mins = fetch_data_from_database(CALCULATOR_DB_PATH, "TotalDamage", ["OpenerDPS", "LoopDPS", "DPS2Mins"])[0]
    data = [(
        characters[0],
        characters[1],
        characters[2],
        opener_dps,
        loop_dps,
        dps2mins,
        build_string
    )]
    append_rows_to_table(CALCULATOR_DB_PATH, "ExecutionHistory", new_data=data)
    UIWindow.find_table_widget_by_name("ExecutionHistory").load_table_data()

# The main method that runs all the calculations and updates the data.
# Yes, I know, it's like an 800 line method, so ugly.

def run_calculations():
    global jinhsi_outro_active, rythmic_vibrato
    
    logger.info("Starting calculations...")
    
    skill_data = {}
    passive_damage_instances = []
    weapon_data = {}
    char_data = {}
    characters = []
    sequences = {}
    last_total_buff_map = {} # the last updated total buff maps for each character
    bonus_stats = {}
    queued_buffs = []
    
    skill_level_multiplier = get_skill_level_multiplier()

    # The "Opener" damage is the total damage dealt before the first main DPS (first character) executes their Outro for the first time.
    opener_damage = 0
    opener_time = 0
    loop_damage = 0
    mode = "opener"

    jinhsi_outro_active = False
    rythmic_vibrato = 0

    level_cap, enemy_level, res = fetch_data_from_database(CALCULATOR_DB_PATH, "Settings", columns=["LevelCap", "EnemyLevel", "Resistance"])[0]

    # Data for stat analysis
    stat_check_map = {
        "attack": 0.086,
        "health": 0.086,
        "defense": 0.109,
        "crit_rate": 0.081,
        "crit_dmg": 0.162,
        "normal": 0.086,
        "heavy": 0.086,
        "skill": 0.086,
        "liberation": 0.086,
        "flat_attack": 40
    }
    char_stat_gains = {}
    char_entries = {}
    total_damage_map = {
        "normal": 0,
        "heavy": 0,
        "skill": 0,
        "liberation": 0,
        "intro": 0,
        "outro": 0,
        "echo": 0
    }
    damage_by_character = {}

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
    
    total_swaps = 0
    
    characters = [character1, character2, character3]
    simulate_active_char_sheet(characters)
    simulate_active_effects_sheet(characters)
    active_buffs["team"] = []
    active_buffs[character1] = []
    active_buffs[character2] = []
    active_buffs[character3] = []

    last_seen = {}
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "TotalDamage", "PreviousTotal", [old_damage])

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
    
    weapon_data = {}
    weapons = get_weapons()
    
    try:
        characters_weapons_range, weapon_rank_range = zip(*fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", columns=["Weapon", "Rank"]))
    except ValueError:
        logger.warning("Aborting calculation because no characters or weapons have been chosen")
        return

    # load echo data into the echo parameter
    echoes = get_echoes()

    for i, character in enumerate(characters):
        weapon_data[character] = character_weapon(weapons[characters_weapons_range[i]], level_cap, weapon_rank_range[i])
        row = fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", where_clause=f"ID = {i + 1}")[0]
        char_data[character] = row_to_character_info(row, level_cap, weapon_data, start_full_reso)
        sequences[character] = char_data[character]["resonance_chain"]

        echo_name = char_data[character]["echo"]
        char_data[character]["echo"] = echoes[echo_name]
        skill_data[echo_name] = char_data[character]["echo"]
        logger.debug(f'setting skill data for echo {echo_name}; echo cd is {char_data[character]["echo"]["cooldown"]}')
        initial_d_cond[character] = {
            "forte": 0,
            "concerto": 0,
            "resonance": 0
        }
        last_seen[character] = -1

    skill_data = {}
    effect_objects = get_skills()
    for effect in effect_objects:
        skill_data[effect["name"]] = effect

    tracked_buffs = [] # Stores the active buffs for each time point.

    # Outro buffs are special, and are saved to be applied to the NEXT character swapped into.
    queued_buffs_for_next = []
    last_character = None

    swapped = False
    all_buffs = get_active_effects(skill_data) # retrieves all buffs "in play" from the ActiveEffects table.

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
                logger.debug(f'adding echo buff {echo_buff["name"]} to {characters[i]}')
                logger.debug(new_buff)

        for weapon_buff in weapon_buff_data:
            if weapon_data[characters[i]]["weapon"]["buff"] in weapon_buff["name"]:
                new_buff = row_to_weapon_buff(weapon_buff, weapon_data[characters[i]]["rank"], characters[i])
                logger.debug(f'adding weapon buff {new_buff["name"]} to {characters[i]}')
                logger.debug(new_buff)
                all_buffs.append(new_buff)

    # apply passive buffs
    for i in range(len(all_buffs) - 1, -1, -1):
        buff = all_buffs[i]
        if buff["triggered_by"] == "Passive" and buff["duration"] == "Passive" and buff.get("special_condition") is None:
            match buff["type"]:
                case "stacking_buff":
                    buff["duration"] = 9999
                    logger.debug(f'passive stacking buff {buff["name"]} applies to: {buff["applies_to"]}; stack interval aka starting stacks: {buff["stack_interval"]}')
                    active_buffs[buff["applies_to"]].append(create_active_stacking_buff(buff, 0, min(buff["stack_interval"], buff["stack_limit"])))
                case "buff":
                    buff["duration"] = 9999
                    logger.debug(f'passive buff {buff["name"]} applies to: {buff["applies_to"]}')
                    active_buffs[buff["applies_to"]].append(create_active_buff(buff, 0))
                    logger.debug(f'adding passive buff : {buff["name"]} to {buff["applies_to"]}')

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
        logger.debug(f"new rotation line: {i}; character: {active_character}; skill: {skills[i]}; time: {times[i]} + {bonus_time_total}")

        if last_character is not None and active_character != last_character: # a swap was performed
            swapped = True
            total_swaps += 1
        current_skill = skills[i] # the current skill
        skill_ref = get_skill_reference(skill_data, current_skill, active_character)
        if swapped and (current_time - last_seen[active_character]) < 1 and not (skill_ref["name"].startswith("Intro") or skill_ref["name"].startswith("Outro")): # add swap-in time
            extra_to_add = 1 - (current_time - last_seen[active_character])
            logger.debug(f'adding extra time. current time: {current_time}; lastSeen: {last_seen[active_character]}; skill: {skill_ref["name"]}; time to add: {1 - (current_time - last_seen[active_character])}')
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
            logger.debug(f'{skill_name}: {skill_track["charges"]}, last used: {skill_track["last_used_time"]}; restored: {restored_charges}; next valid: {skill_track["next_valid_time"]}')

            if skill_track["charges"] > 0:
                if skill_track["charges"] == max_charges: # only update the timer when you're at max stacks to start regenerating the charge
                    skill_track["last_used_time"] = current_time
                skill_track["charges"] -= 1
                cooldown_map[skill_name] = skill_track
            else:
                next_valid_time = skill_track["next_valid_time"]
                logger.debug(f'not enough charges for skill. next valid time: {next_valid_time}')
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
                        if active_buff["buff"]["type"] == "stacking_buff":
                            effective_interval = active_buff["buff"]["stack_interval"]
                            if active_buff["buff"]["name"].startswith("Incandescence") and jinhsi_outro_active:
                                effective_interval = 1
                            logger.debug(f'current_time: {current_time}; active_buff["stack_time"]: {active_buff["stack_time"]}; effective_interval: {effective_interval}')
                            if current_time - active_buff["stack_time"] >= effective_interval:
                                logger.debug(f'updating stacks for {active_buff["buff"]["name"]}: new stacks: {outro_copy["stacks"]} + {active_buff["stacks"]}; limit: {active_buff["buff"]["stack_limit"]}')
                                active_buff["stacks"] = min(active_buff["stacks"] + outro_copy["stacks"], active_buff["buff"]["stack_limit"])
                                active_buff["stack_time"] = current_time
                        else:
                            active_buff["start_time"] = current_time
                            logger.debug(f'updating start_time of {active_buff["buff"]["name"]} to {current_time}')
                if not found: # add a new buff
                    active_set.append(outro_copy)
                    logger.debug(f'adding new buff from queued_buff_for_next: {outro_copy["buff"]["name"]} x{outro_copy["stacks"]}')

                logger.debug(f'Added queued_for_next buff [{queued_buff["buff"]["name"]}] from {last_character} to {active_character}')
                logger.debug(outro_copy)
            queued_buffs_for_next = []
        last_character = active_character
        if len(queued_buffs) > 0: # add queued buffs procced from passive effects
            for queued_buff in queued_buffs:
                found = False
                copy = deepcopy(queued_buff)
                copy["buff"]["applies_to"] = active_character if (copy["buff"]["applies_to"] == "Next" or copy["buff"]["applies_to"] == "Active") else copy["buff"]["applies_to"]
                active_set = active_buffs["team"] if copy["buff"]["applies_to"] == "Team" else active_buffs[copy["buff"]["applies_to"]]

                logger.debug(f'Processing queued buff [{queued_buff["buff"]["name"]}]; applies to {copy["buff"]["applies_to"]}')
                if "consume_buff" in queued_buff["buff"]["type"]: # a queued consumebuff will instantly remove said buffs
                    remove_buff_instant.append(copy["buff"]["classifications"])
                else:
                    for active_buff in active_set: # loop through and look for if the buff already exists
                        if active_buff["buff"]["name"] == copy["buff"]["name"] and active_buff["buff"]["triggered_by"] == copy["buff"]["triggered_by"]:
                            found = True
                            if active_buff["buff"]["type"] == "stacking_buff":
                                effective_interval = active_buff["buff"]["stack_interval"]
                                if active_buff["buff"]["name"].startswith("Incandescence") and jinhsi_outro_active:
                                    effective_interval = 1
                                logger.debug(f'current_time: {current_time}; active_buff["stack_time"]: {active_buff["stack_time"]}; effective_interval: {effective_interval}')
                                if current_time - active_buff["stack_time"] >= effective_interval:
                                    active_buff["stack_time"] = copy["start_time"] # we already calculated the start time based on lastProc
                                    logger.debug(f'updating stacks for {active_buff["buff"]["name"]}: new stacks: {copy["stacks"]} + {active_buff["stacks"]}; limit: {active_buff["buff"]["stack_limit"]}; time: {active_buff["stack_time"]}')
                                    active_buff["stacks"] = min(active_buff["stacks"] + copy["stacks"], active_buff["buff"]["stack_limit"])
                                    active_buff["stack_time"] = current_time; # this actually is not accurate, will fix later. should move forward on multihits
                            else:
                                # sometimes a passive instance-triggered effect that procced earlier gets processed later. 
                                # to work around this, check which activated effect procced later
                                if copy["start_time"] > active_buff["start_time"]:
                                    active_buff["start_time"] = copy["start_time"]
                                    logger.debug(f'updating startTime of {active_buff["buff"]["name"]} to {copy["start_time"]}')
                    if not found: # add a new buff
                        active_set.append(copy)
                        logger.debug(f'adding new buff from queue: {copy["buff"]["name"]} x{copy["stacks"]} at {copy["start_time"]}')
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
                        logger.debug(f'condition not found: {buff["special_condition"]} for skill {skill_ref["name"]}')
                elif ":" in buff["special_condition"]:
                    key, value = buff["special_condition"].split(":", 1)
                    if "Buff" in key: # check the presence of a buff
                        is_activated = False
                        for active_buff in active_set: # loop through and look for if the buff already exists
                            if active_buff["buff"]["name"] == value:
                                is_activated = True
                    else:
                        logger.debug(f'unhandled colon condition: {buff["special_condition"]} for skill {skill_ref["name"]}')
                else:
                    logger.debug(f'unhandled condition: {buff["special_condition"]} for skill {skill_ref["name"]}')
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
                        logger.debug(f'checking for additional condition: {additional_condition}; length: {len(additional_condition)}; skill_ref class: {skill_ref["classifications"]}; skill_ref name: {skill_ref["name"]}; fulfilled? {found}')
                    if found_extra:
                        extra_condition = True
                if extra_condition:
                    if "Buff:" in condition: # check for the existence of a buff
                        buff_name = condition.split(":")[1]
                        logger.debug(f'checking for the existence of {buff_name} at time {current_time}')
                        buff_array = active_buffs[active_character]
                        buff_array_team = active_buffs["team"]
                        buff_names = [
                            f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
                            if active_buff["buff"]["type"] == "stacking_buff"
                            else active_buff["buff"]["name"]
                            for active_buff in buff_array] # Extract the name from each object
                        buff_names_team = [
                            f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
                            if active_buff["buff"]["type"] == "stacking_buff"
                            else active_buff["buff"]["name"]
                            for active_buff in buff_array_team] # Extract the name from each object
                        buff_names_string = ", ".join(buff_names)
                        buff_names_string_team = ", ".join(buff_names_team)
                        if buff_name in buff_names_string or buff_name in buff_names_string_team:
                            is_activated = special_activated
                            break
                    elif condition_is_skill_name:
                        for passive_damage_queued in passive_damage_queue:
                            if (passive_damage_queued is not None
                                and ((condition in passive_damage_queued.name or passive_damage_queued.name in condition)
                                or (condition == "Passive" and passive_damage_queued.limit != 1
                                and (passive_damage_queued.type != "TickOverTime" and buff["can_activate"] != "Active")))
                                and (buff["can_activate"] == passive_damage_queued.owner or buff["can_activate"] in ["Team", "Active"])):
                                logger.debug(f'[skill name] passive damage queued exists - adding new buff {buff["name"]}')
                                passive_damage_queued.add_buff(create_active_stacking_buff(buff, current_time, 1) if buff["type"] == "stacking_buff" else create_active_buff(buff, current_time))
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
                        logger.debug(f'passive damage queued: {passive_damage_queued is not None}, condition: {condition}, name: {passive_damage_queued.name if passive_damage_queued is not None else "none"}, buff["can_activate"]: {buff["can_activate"]}, owner: {passive_damage_queued.owner if passive_damage_queued is not None else "none"}')
                        for passive_damage_queued in passive_damage_queue:
                            if passive_damage_queued is not None and condition in passive_damage_queued.classifications and (buff["can_activate"] == passive_damage_queued.owner or buff["can_activate"] == "Team"):
                                logger.debug(f'passive damage queued exists - adding new buff {buff["name"]}')
                                passive_damage_queued.add_buff(create_active_stacking_buff(buff, current_time, 1) if buff["type"] == "stacking_buff" else create_active_buff(buff, current_time))
                        # the condition is a classification code, check against the classification
                        if (condition in classification or (condition == "Hl" and heal_found)) and (buff["can_activate"] == active_character or buff["can_activate"] == "Team"):
                            is_activated = special_activated
                            break
            if buff["name"].startswith("Incandescence") and "Ec" in skill_ref["classifications"]:
                is_activated = False
            if is_activated: # activate this effect
                found = False
                stacks_to_add = 1
                logger.debug(f'{buff["name"]} has been activated by {skill_ref["name"]} at {current_time}; type: {buff["type"]}; applies_to: {buff["applies_to"]}; class: {buff["classifications"]}')
                if "Hl" in buff["classifications"]: # when a heal effect is procced, raise a flag for subsequent proc conditions
                    heal_found = True
                if buff["type"] == "consume_buff_instant": # these buffs are immediately withdrawn before they are calculating
                    remove_buff_instant.append(buff["classifications"])
                elif buff["type"] == "consume_buff":
                    if remove_buff is not None:
                        logger.debug("UNEXPECTED double removebuff condition.")
                    remove_buff = buff["classifications"]; # remove this later, after other effects apply
                elif buff["type"] == "reset_buff":
                    buff_array = list(active_buffs[active_character])
                    buff_array_team = list(active_buffs["team"])
                    buff_names = [
                        f'{activeBuff["buff"]["name"]} x{active_buff["stacks"]}'
                        if activeBuff["buff"]["type"] == "stacking_buff"
                        else activeBuff["buff"]["name"]
                        for activeBuff in buff_array] # Extract the name from each object
                    buff_names_team = [
                        f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
                        if active_buff["buff"]["type"] == "stacking_buff"
                        else active_buff["buff"]["name"]
                        for active_buff in buff_array_team] # Extract the name from each object
                    buff_names_string = ", ".join(buff_names)
                    buff_names_string_team = ", ".join(buff_names_team)
                    if buff["name"] not in (buff_names_string, buff_names_string_team):
                        logger.debug("adding new active resetbuff")
                        active_set.append(create_active_buff(buff, current_time))
                elif buff["type"] == "dmg": # add a new passive damage instance
                    # queue the passive damage and snapshot the buffs later
                    logger.debug(f'adding a new type of passive damage {buff["name"]}')
                    passive_damage_queued = PassiveDamage(buff["name"], buff["classifications"], buff["buff_type"], buff["amount"], buff["duration"], current_time, buff["stack_limit"], buff["stack_interval"], buff["triggered_by"], active_character, i, buff.get("d_cond"))
                    if buff["buff_type"] == "tick_over_time" and "Inklet" not in buff["name"]:
                        # for DOT effects, procs are only applied at the end of the interval
                        passive_damage_queued.lastProc = current_time
                    passive_damage_queue.append(passive_damage_queued)
                    logger.debug(passive_damage_queued)
                elif buff["type"] == "stacking_buff":
                    effective_interval = buff["stack_interval"]
                    if "Incandescence" in buff["name"] and jinhsi_outro_active:
                        effective_interval = 1
                    logger.debug(f'effective_interval: {effective_interval}; cast_time: {skill_ref["cast_time"]}; hits: {skill_ref["number_of_hits"]}; freeze_time: {skill_ref["freeze_time"]}')
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
                    logger.debug(f'{buff["name"]} is a stacking buff (special condition: {buff["special_condition"]}). attempting to add {stacks_to_add} stacks')
                    for active_buff in active_set: # loop through and look for if the buff already exists
                        if active_buff["buff"]["name"] == buff["name"] and active_buff["buff"]["triggered_by"] == buff["triggered_by"]:
                            found = True
                            logger.debug(f'current stacks: {active_buff["stacks"]} last stack: {active_buff["stack_time"]}; current time: {current_time}')
                            if current_time - active_buff["stack_time"] >= effective_interval:
                                active_buff["stacks"] = min(active_buff["stacks"] + stacks_to_add, buff["stack_limit"])
                                active_buff["stack_time"] = current_time
                                logger.debug("updating stacking buff: " + buff["name"])
                    if not found: # add a new stackable buff
                        active_set.append(create_active_stacking_buff(buff, current_time, min(stacks_to_add, buff["stack_limit"])))
                else:
                    if "Outro" in buff["name"] or buff["applies_to"] == "Next": # outro buffs are special and are saved for the next character
                        queued_buffs_for_next.append(create_active_buff(buff, current_time))
                        logger.debug(f'queuing buff for next: {buff["name"]}')
                    else:
                        for active_buff in active_set: # loop through and look for if the buff already exists
                            if active_buff["buff"]["name"] == buff["name"]:
                                active_buff["start_time"] = current_time + skill_ref["cast_time"]
                                found = True
                                logger.debug(f'updating starttime of {buff["name"]} to {current_time + skill_ref["cast_time"]}')
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
                                if active_buff["buff"]["type"] == "stacking_buff"
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
                        evaluate_d_cond(value * stacks_to_add, condition, i, active_character, characters, char_data, weapon_data, bonus_stats, buff_names, skill_ref, initial_d_cond, total_buff_map)

        for remove_buff in remove_buff_instant:
            if remove_buff is not None:
                for active_buff in active_buffs[active_character]:
                    if remove_buff in active_buff["buff"]["name"]:
                        active_buffs[active_character].remove(active_buff)
                        logger.debug(f'removing buff instantly: {active_buff["buff"]["name"]}')
                for active_buff in active_buffs["team"]:
                    if remove_buff in active_buff["buff"]["name"]:
                        active_buffs["team"].remove(active_buff)
                        logger.debug(f'removing buff instantly: {active_buff["buff"]["name"]}')

        active_buffs_array = active_buffs[active_character]
        buff_names = [
            f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
            if active_buff["buff"]["type"] == "stacking_buff"
            else active_buff["buff"]["name"]
            for active_buff in active_buffs_array] # Extract the name from each object
        buff_names_string = ", ".join(buff_names)

        if len(active_buffs_array) == 0:
            write_buffs_personal.append("(0)")
        else:
            buff_string = f'({len(active_buffs_array)}) {buff_names_string}'
            write_buffs_personal.append(buff_string)

        active_buffs_array_team = active_buffs["Team"]
        buff_names_team = [
            f'{active_buff["buff"]["name"]} x{active_buff["stacks"]}'
            if active_buff["buff"]["type"] == "stacking_buff"
            else active_buff["buff"]["name"]
            for active_buff in active_buffs_array_team] # Extract the name from each object
        buff_names_string_team = ", ".join(buff_names_team)

        logger.debug(f'buff names string team: {buff_names_string_team}')

        if len(buff_names_string_team) == 0:
            write_buffs_team.append("(0)")
        else:
            buff_string = f'({len(active_buffs_array_team)}) {buff_names_string_team}'
            write_buffs_team.append(buff_string)

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

        if weapon_data[active_character]["main_stat"] in total_buff_map:
            total_buff_map[weapon_data[active_character]["main_stat"]] += weapon_data[active_character]["main_stat_amount"]
            logger.debug(f'adding mainstat {weapon_data[active_character]["main_stat"]} (+{weapon_data[active_character]["main_stat_amount"]}) to {active_character}')
        logger.debug("BONUS STATS:")
        logger.debug(char_data[active_character]["bonus_stats"])
        for stat, value in char_data[active_character]["bonus_stats"].items():
            current_amount = total_buff_map.get(stat, 0)
            total_buff_map[stat] = current_amount + value
        process_buffs(active_buffs_array, current_time, char_data, active_character, total_buff_map, skill_ref)

        process_buffs(active_buffs_array_team, current_time, char_data, active_character, total_buff_map, skill_ref)
        last_total_buff_map[active_character] = total_buff_map
        for passive_damage_queued in passive_damage_queue:
            if passive_damage_queued is not None: # snapshot passive damage BEFORE team buffs are applied
                # TEMP: move this above activeBuffsArrayTeam and implement separate buff tracking
                for instance in passive_damage_instances: # remove any duplicates first
                    if instance.name == passive_damage_queued.name:
                        instance.remove = True
                        logger.debug(f'new instance of passive damage {passive_damage_queued.name} found. removing old entry')
                        break
                passive_damage_queued.set_total_buff_map(total_buff_map, sequences)
                passive_damage_instances.append(passive_damage_queued)

        write_buffs_to_sheet(total_buff_map, bonus_stats, char_data, active_character, write_stats)
        if "buff" in skill_ref["type"]:
            overwrite_table_data_by_row_ids(CALCULATOR_DB_PATH, "RotationBuilder", [{"ID": i + 1, "DMG": 0}])
            continue
        
        # damage calculations
        logger.debug(f'DAMAGE CALC for : {skill_ref["name"]}')
        logger.debug(skill_ref)
        logger.debug(f'multiplier: {total_buff_map["multiplier"]}')
        passive_damage_instances = [passive_damage for passive_damage in passive_damage_instances if not passive_damage.can_remove(current_time, remove_buff)]
        for condition, value in skill_ref["d_cond"].items():
            evaluate_d_cond(value, condition, i, active_character, characters, char_data, weapon_data, bonus_stats, buff_names, skill_ref, initial_d_cond, total_buff_map)
        passive_current_slot = False # if a passive damage procs on the same slot, we need to add the damage to the current value later
        if skill_ref["damage"] > 0:
            for passive_damage in passive_damage_instances:
                logger.debug(f'checking proc conditions for {passive_damage.name}; {passive_damage.can_proc(current_time, skill_ref)} ({skill_ref["name"]})')
                if passive_damage.can_proc(current_time, skill_ref) and passive_damage.check_proc_conditions(skill_ref):
                    passive_damage.update_total_buff_map(last_total_buff_map, sequences)
                    procs = passive_damage.handle_procs(current_time, skill_ref["cast_time"] - skill_ref["freeze_time"], skill_ref["number_of_hits"], jinhsi_outro_active, queued_buffs)
                    damage_proc = passive_damage.calculate_proc(active_character, characters, char_data, weapon_data, bonus_stats, last_seen, rythmic_vibrato, level_cap, enemy_level, res, skill_level_multiplier, opener_damage, loop_damage, char_entries, damage_by_character, mode, stat_check_map, char_stat_gains, total_damage_map) * procs
                    if passive_damage.slot == i:
                        set_value_at_index(write_damage, passive_damage.slot, damage_proc)
                        passive_current_slot = True
                    else:
                        add_to_list(write_damage, passive_damage.slot, damage_proc)
                    set_value_at_index(write_damage_note, passive_damage.slot, passive_damage.get_note(skill_level_multiplier))
        write_resonance.append(f'{char_data[active_character]["d_cond"]["resonance"]:.2f}')
        write_concerto.append(f'{char_data[active_character]["d_cond"]["concerto"]:.2f}')

        additive_value_key = f'{skill_ref["name"]} (Additive)'
        damage = skill_ref["damage"] * (1 if ("Ec" in skill_ref["classifications"] or "Ou" in skill_ref["classifications"]) else skill_level_multiplier) + total_buff_map.get(additive_value_key, 0)
        attack = (char_data[active_character]["attack"] + weapon_data[active_character]["attack"]) * (1 + total_buff_map["attack"] + bonus_stats[active_character]["attack"]) + total_buff_map["flat_attack"]
        health = char_data[active_character]["health"] * (1 + total_buff_map["health"] + bonus_stats[active_character]["health"]) + total_buff_map["flat_health"]
        defense = char_data[active_character]["defense"] * (1 + total_buff_map["defense"] + bonus_stats[active_character]["defense"]) + total_buff_map["flat_defense"]
        crit_multiplier = (1 - min(1,(char_data[active_character]["crit_rate"] + total_buff_map["crit_rate"]))) * 1 + min(1,(char_data[active_character]["crit_rate"] + total_buff_map["crit_rate"])) * (char_data[active_character]["crit_dmg"] + total_buff_map["crit_dmg"])
        damage_multiplier = get_damage_multiplier(skill_ref["classifications"], total_buff_map, level_cap, enemy_level, res)
        scale_factor = defense if "Df" in skill_ref["classifications"] else (health if "Hp" in skill_ref["classifications"] else attack)
        total_damage = damage * scale_factor * crit_multiplier * damage_multiplier * (0 if weapon_data[active_character]["weapon"]["name"] == "Nullify Damage" else 1)
        logger.debug(f'skill damage: {damage:.2f}; attack: {(char_data[active_character]["attack"] + weapon_data[active_character]["attack"]):.2f} x {(1 + total_buff_map["attack"] + bonus_stats[active_character]["attack"]):.2f} + {total_buff_map["flat_attack"]}; crit mult: {crit_multiplier:.2f}; dmg mult: {damage_multiplier:.2f}; defense: {defense}; total dmg: {total_damage:.2f}')
        if passive_current_slot:
            add_to_list(write_damage, len(write_damage) - 1, total_damage)
        else:
            write_damage.append(total_damage)
        write_damage_note.append("")

        opener_damage, loop_damage = update_damage(
            name=skill_ref["name"], 
            classifications=skill_ref["classifications"], 
            active_character=active_character, 
            damage=damage, 
            total_damage=total_damage, 
            total_buff_map=total_buff_map, 
            char_entries=char_entries, 
            damage_by_character=damage_by_character, 
            mode=mode, 
            opener_damage=opener_damage, 
            loop_damage=loop_damage, 
            stat_check_map=stat_check_map, 
            char_data=char_data, 
            weapon_data=weapon_data, 
            bonus_stats=bonus_stats, 
            level_cap=level_cap, 
            enemy_level=enemy_level, 
            res=res, 
            char_stat_gains=char_stat_gains, 
            total_damage_map=total_damage_map)
        if mode == "opener" and character1 == active_character and skill_ref["name"].startswith("Outro"):
            mode = "loop"
            opener_time = fetch_data_from_database(CALCULATOR_DB_PATH, "RotationBuilder", columns="InGameTime", where_clause=f"ID = {i + 1}")[0]
        live_time += skill_ref["cast_time"] # live time

        if remove_buff is not None:
            for active_buff in active_buffs[active_character]:
                if remove_buff in active_buff["buff"]["name"]:
                    active_buffs[active_character].remove(active_buff)
                    logger.debug(f'removing buff: {active_buff["buff"]["name"]}')
            for active_buff in active_buffs["team"]:
                if remove_buff in active_buff["buff"]["name"]:
                    active_buffs["team"].remove(active_buff)
                    logger.debug(f'removing buff: {active_buff["buff"]["name"]}')

    logger.debug("===EXECUTION COMPLETE===")
    logger.debug("updating cells...")

    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "RotationBuilder", "Resonance", write_resonance)
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "RotationBuilder", "Concerto", write_concerto)
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "RotationBuilder", "LocalBuffs", write_buffs_personal)
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "RotationBuilder", "GlobalBuffs", write_buffs_team)
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "RotationBuilder", [
        "AttackMultiplier", 
        "HealthMultiplier", 
        "DefenseMultiplier", 
        "CritRateMultiplier", 
        "CritDmgMultiplier", 
        "NormalBonus", 
        "HeavyBonus", 
        "SkillBonus", 
        "LiberationBonus", 
        "NormalAmp", 
        "HeavyAmp", 
        "SkillAmp", 
        "LiberationAmp", 
        "PhysicalBonus", 
        "GlacioBonus", 
        "FusionBonus", 
        "ElectroBonus", 
        "AeroBonus", 
        "SpectroBonus", 
        "HavocBonus", 
        "Bonus", 
        "Amplify", 
        "Multiplier", 
        "MinusRes", 
        "IgnoreDefense"
    ], write_stats)
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "RotationBuilder", "DMG", write_damage)

    for i, note in enumerate(write_damage_note):
        if len(note) > 0: # only write if there's actually something
            UIWindow.find_table_widget_by_name("RotationBuilder").set_cell_attributes(
                "DMG", i, 
                note=note, 
                font_weight=QFont.Bold)

    final_time = fetch_data_from_database(CALCULATOR_DB_PATH, "RotationBuilder", columns="InGameTime", where_clause=f"ID = {len(skills)}")[0]
    logger.debug(f'real time: {live_time}; final in-game time: {final_time}')
    UIWindow.find_table_widget_by_name("TotalDamage").set_cell_attributes(
        "Opener DPS", 0, 
        note=f'Total Damage: {opener_damage:.2f} in {opener_time:.2f}s', 
        font_weight=QFont.Bold)
    UIWindow.find_table_widget_by_name("TotalDamage").set_cell_attributes(
        "Loop DPS", 0, 
        note=f'Total Damage: {loop_damage:.2f} in {(final_time - opener_time):.2f}s', 
        font_weight=QFont.Bold)
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "TotalDamage", "OpenerDPS", [opener_damage / opener_time if opener_time > 0 else 0])
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "TotalDamage", "LoopDPS", [loop_damage / (final_time - opener_time)])

    w_dps_loop_time = 120 - opener_time
    w_dps_loops = w_dps_loop_time / (final_time - opener_time)
    w_dps = (opener_damage + loop_damage * w_dps_loops) / 120

    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "TotalDamage", "Complexity", [total_swaps + (len(skills) - 1) / (final_time / 60)])
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "TotalDamage", "DPS2Mins", [f'{w_dps:.2f}'])

    config = load_config(CONFIG_PATH)
    calculator_tables = config[CALCULATOR_DB_PATH]["tables"]
    
    for table in calculator_tables:
        if table["table_name"] == "NextSubstatValue":
            next_substat_value_table = table
            break
    
    if not next_substat_value_table:
        raise ValueError("InherentSkills table not found in the configuration.")
    
    db_columns = next_substat_value_table["db_columns"]
    total_columns = len(db_columns.keys())
    table_data = [[character] for character in characters]
    
    for i, character in enumerate(characters):
        data_row = None
        if char_entries[character] > 0: # Using [character] to get each character's entry
            stats = char_stat_gains[character]

            for key in stats.keys():
                if damage_by_character[character] == 0:
                    stats[key] = 0
                else:
                    stats[key] /= damage_by_character[character] # char_entries[character]
            logger.debug(char_stat_gains[character])
            data_row = list(stats.values())

        data_row = pad_and_insert_rows([data_row], total_columns=total_columns - 1)[0]
        table_data[i].extend(data_row)

    overwrite_table_data(CALCULATOR_DB_PATH, "NextSubstatValue", db_columns, table_data)

    logger.debug(total_damage_map)
    overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "TotalDamage", ["Normal", "Heavy", "Skill", "Liberation", "Intro", "Outro", "Echo"], [list(total_damage_map.values())])

    # write initial and final dconds

    for i, character in enumerate(characters):
        damage_sum = fetch_data_from_database(CALCULATOR_DB_PATH, "RotationBuilder", "SUM(DMG)", where_clause=f"Character = '{character}'")
        overwrite_table_data_by_columns(CALCULATOR_DB_PATH, "TotalDamage", f'Character{i + 1}', damage_sum)

        overwrite_table_data_by_row_ids(CALCULATOR_DB_PATH, "EnergyCalculation", [{
            "ID": i + 1, 
            "Character": character, 
            "ForteInitial": initial_d_cond[character]["forte"], 
            "ResonanceInitial": initial_d_cond[character]["resonance"], 
            "ConcertoInitial": initial_d_cond[character]["concerto"], 
            "ForteFinal": char_data[character]["d_cond"]["forte"],
            "ResonanceFinal": char_data[character]["d_cond"]["resonance"], 
            "ConcertoFinal": char_data[character]["d_cond"]["concerto"]
        }])

    save_to_execution_history(characters, generate_build_string())

    # Output the tracked buffs for each time point (optional)
    for entry in tracked_buffs:
        logger.debug(f'Time: {entry["time"]}, Active Buffs: {", ".join(entry["active_buffs"])}')

    UIWindow.find_table_widget_by_name("RotationBuilder").load_table_data()
    
    logger.info("Calculations finished")

UIWindow.initialize_calc_tables_signal.connect(initialize_calc_tables)
UIWindow.run_calculations_signal.connect(run_calculations)
UIWindow.import_build_signal.connect(import_build)
UIWindow.export_build_signal.connect(export_build)

sys.exit(app.exec_())