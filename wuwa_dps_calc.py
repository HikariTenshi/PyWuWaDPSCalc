import logging
from copy import deepcopy
from functools import cmp_to_key
from utils.database_io import fetch_data_comparing_two_databases, fetch_data_from_database, initialize_database
from utils.config_io import load_config

VERSION = "V3.3.3"
CONSTANTS_DB_PATH = "databases/constants.db"
CALCULATOR_DB_PATH = "databases/calculator.db"
CONFIG_PATH = "databases/table_config.json"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHECK_STATS = True

STANDARD_BUFF_TYPES = ["Normal", "Heavy", "Skill", "Liberation"]
ELEMENTAL_BUFF_TYPES = ["Glacio", "Fusion", "Electro", "Aero", "Spectro", "Havoc"]

def initialize_calc_tables(db_name=CALCULATOR_DB_PATH, config_path=CONFIG_PATH):
    """
    Initialize database tables based on configuration settings.

    This function loads the configuration from a JSON file and initializes each table
    specified in the configuration. For each table, it will create the table if it does
    not already exist and optionally insert initial data if provided.

    :param db_name:
        The path to the database file where tables will be initialized. 
        Defaults to `CALCULATOR_DB_PATH`.
    :type db_name: str, optional
    :param config_path:
        The path to the JSON configuration file that contains the table setup information.
        Defaults to `CONFIG_PATH`.
    :type config_path: str, optional

    :raises FileNotFoundError: If the configuration file is not found at the specified path.
    :raises KeyError: If the database name is not found in the configuration file.
    :raises Exception: If there is an issue with loading the configuration or initializing tables.

    :return: None
    """
    config = load_config(config_path)
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

skill_data = []
passive_damage_instances = []
weapon_data = {}
char_data = {}
characters = []
sequences = []
lastTotalBuffMap = {} # the last updated total buff maps for each character
bonus_stats = []
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
openerDamage = 0
openerTime = 0
loopDamage = 0
mode = "Opener"

jinhsiOutroActive = False
rythmicVibrato = 0

startFullReso = False

# Data for stat analysis
statCheckMap = {
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
totalDamageMap = {
    "Normal": 0,
    "Heavy": 0,
    "Skill": 0,
    "Liberation": 0,
    "Intro": 0,
    "Outro": 0,
    "Echo": 0
}
damageByCharacter = {}

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
        "duration": "Passive" if weapon_buff["duration"] == "Passive" or weapon_buff["duration"] == 0 else new_duration, # slash delimited - how long the buff lasts - a duration is 0 indicates a passive
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
        "mainStat": p_weapon["base_main_stat"],
        "mainStatAmount": p_weapon["baseMainStatAmount"] * WEAPON_MULTIPLIERS[p_level_cap][1],
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