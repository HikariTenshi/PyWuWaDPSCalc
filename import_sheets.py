"""
Wuwa DPS Calculator Database Importer
=====================================

by @HikariTenshi
credit to @Maygi for the original calculator

This module imports data from Google Sheets into an SQLite database. It includes functions to
fetch data from Google Sheets and uses the database_io module to handle database operations.
"""

import os
import sys
import gspread
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime
import time
import logging
from utils.database_io import create_metadata_table, get_last_update_timestamp, update_metadata, update_table
from utils.config_io import load_config

VERSION = "V3.2.12"
CONSTANTS_DB_PATH = "databases/constants.db"
CONFIG_PATH = "databases/table_config.json"
CHARACTERS_DB_PATH = "databases/characters/"
CREDENTIALS_PATH = "credentials/credentials.json"
TOKEN_PATH = "credentials/token.json"
SHEET_URL="https://docs.google.com/spreadsheets/d/1vTbG2HfkVxyqvNXF2taikStK-vJJf40QrWa06Fgj17c/edit#gid=0"
SHEET_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.metadata.readonly"]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QuotaExceededError(Exception):
    """
    Exception raised when a quota limit is exceeded.

    :param message: A message describing the quota limit issue.
    :type message: str
    :param retries: The number of retries attempted before exceeding the quota.
    :type retries: int
    """
    def __init__(self, message, retries=None):
        """
        Initialize the QuotaExceededError.

        :param message: A message describing the quota limit issue.
        :type message: str
        :param retries: The number of retries attempted before exceeding the quota.
        :type retries: int, optional
        """
        super().__init__(message)
        self.retries = retries

    def __str__(self):
        """
        Return a string representation of the error message.

        :return: The error message with retries information if available.
        :rtype: str
        """
        if self.retries is not None:
            return f"{self.message} (Retries attempted: {self.retries})"
        return self.message

def parse_sheet_last_modified(sheet_last_modified):
    """
    Parse the sheet_last_modified timestamp into a datetime object.

    :param sheet_last_modified: The last modified time of the sheet.
    :type sheet_last_modified: str or datetime
    :return: Parsed datetime object.
    :rtype: datetime
    :raises TypeError: If the input is not a datetime object or a string.
    """
    if isinstance(sheet_last_modified, datetime):
        return sheet_last_modified
    elif isinstance(sheet_last_modified, str):
        return datetime.strptime(sheet_last_modified, SHEET_TIME_FORMAT)
    else:
        raise TypeError(f"{sheet_last_modified = } must be a datetime object or a string")

def retry_on_quota_exceeded(func, *args, retries=3, delay=60):
    """
    Retries the execution of a function if a quota exceeded error (HTTP 429) occurs.

    :param func: The function to be executed.
    :type func: function
    :param args: Arguments to pass to the function.
    :type args: tuple
    :param retries: Number of retries before giving up, defaults to 3.
    :type retries: int, optional
    :param delay: Delay between retries in seconds, defaults to 60.
    :type delay: int, optional
    :raises QuotaExceededError: If the maximum number of retries is exceeded.
    :return: The result of the function if successful.
    :rtype: Any
    """
    for _ in range(retries):
        try:
            time.sleep(1) # Trying to avoid hitting the quota
            return func(*args)
        except gspread.exceptions.APIError as e:
            if e.response.status_code != 429:
                raise
            logger.warning("Quota exceeded, retrying in a minute...")
            time.sleep(delay)
    raise QuotaExceededError("Exceeded maximum retries due to quota limits", retries)

def get_sheet_last_modified_time(sheet_id, credentials):
    """
    Get the last modified time of the Google Sheet.

    :param sheet_id: The ID of the Google Sheet.
    :type sheet_id: str
    :param credentials: The Google API credentials.
    :type credentials: google.oauth2.credentials.Credentials
    :return: The last modified time as a datetime object.
    :rtype: datetime
    """
    # Build the Google Drive API service with the given credentials
    service = build("drive", "v3", credentials=credentials)
    
    # Fetch the sheet's metadata to get the last modified time
    sheet_metadata = retry_on_quota_exceeded(service.files().get(fileId=sheet_id, fields="modifiedTime").execute)
    
    # Convert the modified time to a datetime object
    modified_time = sheet_metadata["modifiedTime"]
    return datetime.strptime(modified_time, SHEET_TIME_FORMAT)

def load_credentials(token_path):
    """
    Load credentials from the token file.

    :param token_path: The path to the token file.
    :type token_path: str
    :return: The Google API credentials if the token file exists, None otherwise.
    :rtype: Credentials or None
    """
    if os.path.exists(token_path):
        return Credentials.from_authorized_user_file(token_path, SCOPES)
    return None

def save_credentials(token_path, creds):
    """
    Save the credentials to the token file.

    :param token_path: The path to the token file.
    :type token_path: str
    :param creds: The Google API credentials to save.
    :type creds: Credentials
    """
    with open(token_path, "w") as token:
        token.write(creds.to_json())

def get_new_credentials(credentials_path):
    """
    Prompt the user to log in and get new credentials.

    :param credentials_path: The path to the credentials file.
    :type credentials_path: str
    :return: The new Google API credentials after user logs in.
    :rtype: Credentials
    """
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    return flow.run_local_server(port=0)

def refresh_credentials(creds):
    """
    Refresh the credentials.

    :param creds: The Google API credentials to refresh.
    :type creds: Credentials
    :raises RefreshError: If the Token has expired or been revoked and refreshing it has failed.
    """
    creds.refresh(Request())

def authenticate_google_sheets(credentials_path=CREDENTIALS_PATH, token_path=TOKEN_PATH):
    """
    Authenticate with Google Sheets API and get the gspread client and credentials.

    :param credentials_path: The path to the credentials file.
    :type credentials_path: str, optional
    :param token_path: The path to the token file.
    :type token_path: str, optional
    :return: A tuple containing the gspread client and the Google API credentials.
    :rtype: tuple
    :raises RefreshError: If the Token has expired or been revoked and refreshing it has failed.
    """
    max_retries = 3
    retries = 0
    
    while retries < max_retries:
        creds = load_credentials(token_path)

        # If there are no valid credentials available, prompt the user to log in
        if creds and creds.expired and creds.refresh_token:
            try:
                refresh_credentials(creds)
            except RefreshError as e:
                # Delete the token file to force re-authentication
                os.remove(token_path)
                retries += 1
                if retries >= max_retries:
                    logger.critical("Maximum retries reached. Aborting.")
                    raise RefreshError(
                        "Maximum retries reached. Token has been expired or revoked."
                    ) from e
                logger.warning("Token expired or revoked. Retrying authentication.")
                continue # Retry authentication
        elif not creds or not creds.valid:
            # Save the credentials for the next run
            creds = get_new_credentials(credentials_path)
            save_credentials(token_path, creds)

        # Create a gspread client using the authenticated credentials
        client = gspread.authorize(creds)
        return client, creds

    logger.critical("Authentication failed after maximum retries.")
    raise RefreshError("Authentication failed after maximum retries.")

def get_worksheets(sheet, sheet_titles):
    """
    Get the worksheets from the Google Sheet by their titles.

    :param sheet: The Google Sheet object.
    :type sheet: gspread.models.Spreadsheet
    :param sheet_titles: A list of worksheet titles.
    :type sheet_titles: list
    :return: A dictionary of worksheet titles and their corresponding worksheet objects.
    :rtype: dict
    """
    return {title: sheet.worksheet(title) for title in sheet_titles}

def find_worksheet_range(worksheet_list, start_title, end_title):
    """
    Find the range of worksheets between two specified worksheets.

    :param worksheet_list: A list of worksheet objects.
    :type worksheet_list: list
    :param start_title: The title of the start worksheet.
    :type start_title: str
    :param end_title: The title of the end worksheet.
    :type end_title: str
    :return: A list of worksheets between the start and end worksheets.
    :rtype: list
    :raises ValueError: If the specified worksheets are not found or are in the wrong order.
    """
    start_index, end_index = None, None
    for index, worksheet in enumerate(worksheet_list):
        if worksheet.title == start_title:
            start_index = index
        if worksheet.title == end_title:
            end_index = index
        if start_index is not None and end_index is not None:
            break
    if start_index is None or end_index is None:
        raise ValueError("Specified worksheets not found")
    if start_index >= end_index:
        raise ValueError(
            f"Start sheet must be before end sheet:\n"
            f"worksheet_list = {worksheet_list}\n"
            f"start_title = {start_title}\n"
            f"end_title = {end_title}\n"
            f"start_index = {start_index}\n"
            f"end_index = {end_index}"
            )
    return worksheet_list[start_index + 1:end_index]

def fetch_first_cell_of_last_row(worksheet, start_cell):
    """
    Fetch the first cell of the last non-empty row in a worksheet.

    :param worksheet: The worksheet object.
    :type worksheet: gspread.models.Worksheet
    :param start_cell: The starting cell for the search.
    :type start_cell: str
    :return: The value of the first cell of the last non-empty row.
    :rtype: str or None
    """
    # Determine the starting row and column
    start_row = int("".join(filter(str.isdigit, start_cell)))
    start_col = "".join(filter(str.isalpha, start_cell))

    # Fetch all values in the starting column
    start_col_index = ord(start_col.upper()) - ord("A") + 1
    column_data = retry_on_quota_exceeded(worksheet.col_values, start_col_index)

    # Find the first cell of the last non-empty row
    return next(
        (
            column_data[row_index]
            for row_index in reversed(range(start_row - 1, len(column_data)))
            if column_data[row_index].strip()
        ),
        None,
    )

def convert_percentage_to_float(value, precision=4):
    """
    Convert a percentage string to a float, rounded to a specified precision.

    :param value: The value to convert.
    :type value: str
    :param precision: The number of decimal places to round to.
    :type precision: int
    :return: The converted float value, or the original value if conversion is not possible.
    :rtype: float or str
    """
    if isinstance(value, str) and value.endswith('%'):
        try:
            return round(float(value.rstrip('%')) / 100, precision)
        except ValueError:
            return value  # Return the original value if it cannot be converted
    try:
        return round(float(value), precision)
    except ValueError:
        return value  # Return the original value if it cannot be converted

def fetch_table_data(worksheet, start_cell, end_col):
    """
    Fetch data from a worksheet within a specified column range but unspecified row length.

    :param worksheet: The worksheet object.
    :type worksheet: gspread.models.Worksheet
    :param start_cell: The starting cell for the range.
    :type start_cell: str
    :param end_col: The ending column for the range.
    :type end_col: str
    :return: The fetched table data.
    :rtype: list
    """
    # Determine the starting row and column
    start_row = int("".join(filter(str.isdigit, start_cell)))
    start_col = "".join(filter(str.isalpha, start_cell))

    # Fetch all rows from the start cell to the end column
    column_data = retry_on_quota_exceeded(worksheet.get_all_values)
    
    # Convert column letters to indices
    start_col_index = ord(start_col.upper()) - ord("A")
    end_col_index = ord(end_col.upper()) - ord("A")

    table_data = []
    for row in column_data[start_row-1:]:
        # Extend row if necessary to ensure it has enough columns
        extended_row = row + [''] * (end_col_index + 1 - len(row))
        # Slice the row to include only the relevant columns
        sliced_row = extended_row[start_col_index:end_col_index + 1]
        # Check if the row is empty (all elements are empty strings)
        if any(cell.strip() for cell in sliced_row):
            table_data.append([
                convert_percentage_to_float(cell)
                if cell.endswith("%") else cell
                for cell in sliced_row])

    return table_data

def fetch_table_data_by_range(worksheet, cell_range):
    """
    Fetch data from a worksheet within a specified cell range.

    :param worksheet: The worksheet object.
    :type worksheet: gspread.models.Worksheet
    :param cell_range: The cell range to fetch data from.
    :type cell_range: str
    :return: The fetched table data.
    :rtype: list
    """
    cell_values = retry_on_quota_exceeded(worksheet.range, cell_range)
    
    table_data = []
    row_data = []
    prev_row = cell_values[0].row

    for cell in cell_values:
        if cell.row != prev_row:
            if any(row_data):  # Check if the row contains any non-empty cells
                table_data.append([
                    convert_percentage_to_float(cell)
                    if cell.endswith("%")
                    else cell for cell in row_data])
            row_data = []
            prev_row = cell.row
        row_data.append(cell.value)

    if any(row_data):  # Check the last row as well
        table_data.append([
            convert_percentage_to_float(cell)
            if cell.endswith("%")
            else cell for cell in row_data])

    # Filter out empty rows
    return [
        row
        for row in table_data
        if any(cell is not None and cell.strip() != "" for cell in row)
    ]

def collect_required_worksheets(config, db_name):
    """
    Collect the titles of the required worksheets from the configuration.

    :param config: The configuration dictionary.
    :type config: dict
    :param db_name: The name of the database.
    :type db_name: str
    :return: A set of required worksheet titles.
    :rtype: set
    """
    required_worksheets = set()
    if db_name in config:
        db_config = config[db_name]
        for table in db_config["tables"]:
            required_worksheets.add(table["fetch_args"][0])  # First argument should be the worksheet name
    return required_worksheets

def process_tables_from_config(db_name, tables, worksheets):
    """
    Process and update the tables defined in the configuration.

    :param db_name: The name of the database.
    :type db_name: str
    :param tables: A list of table configurations.
    :type tables: list
    :param worksheets: A dictionary of worksheet titles and their corresponding worksheet objects.
    :type worksheets: dict
    """
    for table in tables:
        fetch_function_name = table["fetch_function"]
        fetch_function = globals()[fetch_function_name]
        fetch_args = [worksheets[arg] if arg in worksheets else arg for arg in table["fetch_args"]]
        update_table(
            db_name,
            table["table_name"],
            table["db_columns"],
            fetch_function,
            fetch_args,
            table["expected_columns"]
        )

def replace_placeholders(fetch_args, character_worksheet):
    """
    Replace placeholders in the fetch arguments with the actual worksheet object.

    :param fetch_args: The list of fetch arguments.
    :type fetch_args: list
    :param character_worksheet: The worksheet object to replace the placeholder with.
    :type character_worksheet: gspread.models.Worksheet
    :return: The updated fetch arguments.
    :rtype: list
    """
    return [character_worksheet if arg == "{character_name}" else arg for arg in fetch_args]

def handle_special_cases(table, fetch_args):
    """
    Handle special cases for certain character worksheets and table configurations.

    :param table: The table configuration dictionary.
    :type table: dict
    :param fetch_args: The arguments to be passed to the fetch function.
    :type fetch_args: list
    :return: Updated fetch function name, fetch arguments and expected columns.
    :rtype: tuple
    """
    fetch_function_name = table["fetch_function"]
    expected_columns = table["expected_columns"]
    worksheet_name = fetch_args[0].title

    # Special case for Changli and Jiyan Resonance Chains
    if table["table_name"] == "ResonanceChains":
        if worksheet_name == "Changli":
            fetch_args = [fetch_args[0], "A30:K37"]
        elif worksheet_name == "Jiyan":
            fetch_args = [fetch_args[0], "A29:K37"]
    
    # Special case for Encore Skills
    elif table["table_name"] == "Skills" and worksheet_name == "Encore":
        fetch_function_name = "fetch_table_data_by_range"
        fetch_args = [fetch_args[0], "A39:L60"]
    
    # Special case for Outros
    elif table["table_name"] == "Outro":
        if worksheet_name == "Encore":
            expected_columns = ["Outro", "DMG %", "Time", "", "Modifier", "Hits"]
        if worksheet_name in ["Yinlin", "Jinhsi", "Danjin"]:
            expected_columns = ["Outro", "DMG %", "Time", "DPS", "Modifier", "Hits", "Forte"]
        if worksheet_name == "Rover (Havoc)":
            expected_columns = ["Outro", "DMG %", "Time", "DPS", "Modifier", "Hits", "Forte", "Concerto"]

    return fetch_function_name, fetch_args, expected_columns

def process_character_worksheets(character_worksheet_list, character_tables):
    """
    Process and update the character worksheets.

    :param character_worksheet_list: A list of character worksheet objects.
    :type character_worksheet_list: list
    :param character_tables: A list of character table configurations.
    :type character_tables: list
    """
    for character_worksheet in character_worksheet_list:
        db_name = f"{CHARACTERS_DB_PATH}{character_worksheet.title}.db"

        for table in character_tables:
            fetch_args = replace_placeholders(table["fetch_args"], character_worksheet) # Evaluate the {character name} placeholder
            
            # Handle special cases
            fetch_function_name, fetch_args, expected_columns = handle_special_cases(table, fetch_args)
            fetch_function = globals()[fetch_function_name]

            update_table(
                db_name,
                table["table_name"],
                table["db_columns"],
                fetch_function,
                fetch_args,
                expected_columns
            )

def process_sheet_data_and_update_db(sheet, config_path, constants_db_name, sheet_last_modified):
    """
    Process data from the Google Sheet and update the SQLite database.

    :param sheet: The Google Sheet object.
    :type sheet: gspread.Spreadsheet
    :param config_path: The path to the configuration file.
    :type config_path: str
    :param constants_db_name: The name of the constants database.
    :type constants_db_name: str
    :param sheet_last_modified: The timestamp of the last modification of the Google Sheet.
    :type sheet_last_modified: datetime
    """
    # Find all character worksheets between "Rotation Samples" and "RotaSkills"
    worksheet_list = sheet.worksheets()
    character_worksheet_list = find_worksheet_range(worksheet_list, "Rotation Samples", "RotaSkills")

    # Load config
    config = load_config(config_path)

    # Collect all required worksheets from config
    required_worksheet_titles = collect_required_worksheets(config, constants_db_name)
    required_worksheets = get_worksheets(sheet, required_worksheet_titles)

    # Update tables
    tables = config.get(constants_db_name)["tables"]
    process_tables_from_config(constants_db_name, tables, required_worksheets)

    # Process character worksheets
    character_tables = config.get("characters", {}).get("tables", [])
    process_character_worksheets(character_worksheet_list, character_tables)

    # Update the metadata (timestamp, version) at the very end
    latest_version = fetch_first_cell_of_last_row(sheet.worksheet("Version Log"), "A3")
    metadata = {
        "timestamp": sheet_last_modified,
        "version": latest_version
    }
    update_metadata(constants_db_name, metadata)

    # Give a warning if Maygi has updated the latest spreadsheet version
    if latest_version != VERSION:
        logger.warning(f"Spreadsheet version ({latest_version}) does not match the script version ({VERSION}), expect things to break at any moment")

def update_sqlite_from_google_sheets(sheet_url, config_path=CONFIG_PATH, constants_db_name=CONSTANTS_DB_PATH):
    """
    Main function to import data from Google Sheets to SQLite.

    :param sheet_url: The URL of the Google Sheet.
    :type sheet_url: str
    :param config_path: The path to the configuration file.
    :type config_path: str
    :param constants_db_name: The name of the constants database.
    :type constants_db_name: str
    """
    logger.info(f"{VERSION = }")
    
    # Authenticate and get both the client and credentials
    try:
        client, credentials = authenticate_google_sheets()
    except RefreshError:
        logger.critical("Exiting the program due to authentication failure.")
        sys.exit(1)

    # Open the Google Sheet
    sheet = retry_on_quota_exceeded(client.open_by_url, sheet_url)
    sheet_id = sheet_url.split("/")[5]

    # Get the last update timestamp from the Google Drive API
    sheet_last_modified_str = get_sheet_last_modified_time(sheet_id, credentials)
    sheet_last_modified = parse_sheet_last_modified(sheet_last_modified_str)

    # Ensure the metadata table exists to store the timestamp and version in
    create_metadata_table(constants_db_name)

    # Check if updates are needed
    last_update_timestamp = get_last_update_timestamp(constants_db_name)
    if last_update_timestamp is None or sheet_last_modified > last_update_timestamp:
        process_sheet_data_and_update_db(
            sheet, config_path, constants_db_name, sheet_last_modified
        )
    else:
        logger.info("No updates needed.")

# Call to main function
update_sqlite_from_google_sheets(SHEET_URL)