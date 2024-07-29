"""
Wuwa DPS Calculator Database Importer
=====================================

by @HikariTenshi
credit to @Maygi for the original calculator

This module imports data from Google Sheets into an SQLite database. It includes functions to
initialize the database, fetch data from Google Sheets, and update the database tables.
"""

import json
import os
import sqlite3
import gspread
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime
import time
import logging

VERSION = "V3.2.10"
SHEET_URL="https://docs.google.com/spreadsheets/d/1vTbG2HfkVxyqvNXF2taikStK-vJJf40QrWa06Fgj17c/edit?gid=347178972#gid=347178972"
SHEET_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DB_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
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

class ValidationError(Exception):
    """
    Exception raised for errors in the validation of data.

    :param message: A message describing the validation error.
    :type message: str
    :param expected_values: The expected values that were used for validation.
    :type expected_values: iterable
    :param given_values: The values that were actually provided and validated.
    :type given_values: iterable
    """
    def __init__(self, message, expected_values, given_values):
        """
        Initialize the ValidationError with a message, expected values, and given values.

        :param message: A message describing the validation error.
        :type message: str
        :param expected_values: The expected values that were used for validation.
        :type expected_values: iterable
        :param given_values: The values that were actually provided and validated.
        :type given_values: iterable
        """
        super().__init__(message)
        self.expected_values = expected_values
        self.given_values = given_values

    def find_ordered_mismatches(self, iterable1, iterable2):
        """
        Find ordered mismatches between two iterables.

        :param iterable1: The first iterable to compare.
        :type iterable1: iterable
        :param iterable2: The second iterable to compare.
        :type iterable2: iterable
        :return: A tuple containing:
                - A list of tuples where each tuple represents an index and the differing values at that index.
                - The number of excess elements in each iterable.
        :rtype: tuple
        """
        mismatches = []
        max_length = max(len(iterable1), len(iterable2))

        for i in range(max_length):
            val1 = iterable1[i] if i < len(iterable1) else None
            val2 = iterable2[i] if i < len(iterable2) else None

            if val1 != val2:
                mismatches.append((i, val1, val2))

        excess_in_1 = len(iterable1) - len(iterable2)
        excess_in_2 = len(iterable2) - len(iterable1)
        
        return mismatches, excess_in_1, excess_in_2

    def __str__(self):
        """
        Return a string representation of the validation error, including mismatches and excess information.

        :return: A string describing the validation error, including expected values, given values, mismatches, and excess counts.
        :rtype: str
        """
        mismatches, excess_expected, excess_given = self.find_ordered_mismatches(self.expected_values, self.given_values)
        return (
            f"{self.message}\n"
            f"Expected values: {self.expected_values}\n"
            f"Given values:    {self.given_values}\n"
            f"Mismatches: {mismatches}\n"
            f"Excess in expected values: {excess_expected}\n"
            f"Excess in given values:    {excess_given}\n"
        )

def load_config(config_path):
    """
    Load the configuration from a JSON file.

    :param config_path: The path to the configuration file.
    :type config_path: str
    :return: The configuration as a dictionary.
    :rtype: dict
    """
    with open(config_path, "r") as config_file:
        return json.load(config_file)

def create_metadata_table(main_db_name):
    """
    Create a metadata table in the database if it doesn't exist.

    :param main_db_name: The name of the main database.
    :type main_db_name: str
    """
    conn = sqlite3.connect(main_db_name)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    conn.commit()
    conn.close()

def initialize_database(db_name, table_name, db_columns):
    """
    Initialize the database and create the specified table with the given columns.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    """
    # Ensure the directory exists
    directory = os.path.dirname(db_name)
    if not os.path.exists(directory) and directory != "":
        os.makedirs(directory)

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Create table with dynamic columns, types, and an auto-increment primary key if it doesn't exist
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        {', '.join([f'{col} {dtype}' for col, dtype in db_columns.items()])}
    )
    """
    cursor.execute(create_table_query)
    conn.commit()
    conn.close()

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

def get_last_update_timestamp(main_db_name):
    """
    Get the last update timestamp from the metadata table.

    :param main_db_name: The name of the main database.
    :type main_db_name: str
    :return: The last update timestamp.
    :rtype: datetime or None
    """
    conn = sqlite3.connect(main_db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
    result = cursor.fetchone()
    conn.close()
    return datetime.strptime(result[0], DB_TIME_FORMAT) if result else None

def update_metadata(main_db_name, metadata):
    """
    Update the metadata table with the provided metadata.

    :param main_db_name: The name of the main database.
    :type main_db_name: str
    :param metadata: The metadata to be updated (should include timestamp and version).
    :type metadata: dict
    """
    conn = sqlite3.connect(main_db_name)
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO metadata (key, value) VALUES ('last_updated', ?)", (metadata["timestamp"],))
    cursor.execute("REPLACE INTO metadata (key, value) VALUES ('version', ?)", (metadata["version"],))
    conn.commit()
    conn.close()

def validate_columns(table_data, expected_columns, db_name, table_name):
    """
    Validate if the table data's first row matches the expected columns.

    :param table_data: The data to be validated.
    :type table_data: list
    :param expected_columns: The expected column names.
    :type expected_columns: list
    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :raises ValidationError: If the column names do not match the expected columns.
    """
    if table_data[0][:len(expected_columns)] != expected_columns:
        raise ValidationError(
            f"Column names for the table {table_name} in database {db_name} do not match the expected columns:\n",
            expected_columns,
            table_data[0]
        )

def insert_data(cursor, table_data, db_columns, table_name):
    """
    Insert data into the database table.

    :param cursor: The database cursor.
    :type cursor: sqlite3.Cursor
    :param table_data: The data to be inserted.
    :type table_data: list
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    :param table_name: The name of the table.
    :type table_name: str
    :raises ValueError: If there is a programming error in the SQL query.
    """
    for row in table_data[1:]:
        # Replace empty values with None (NULL) if necessary
        row = [None if cell == "" else cell for cell in row]
        placeholders = ", ".join(["?"] * len(db_columns))
        insert_query = f"INSERT INTO {table_name} ({', '.join(db_columns.keys())}) VALUES ({placeholders})"
        try:
            cursor.execute(insert_query, row)
        except sqlite3.ProgrammingError as e:
            raise ValueError(
                f"{e}\n"
                f"insert_query = {insert_query}\n"
                f"row = {row}"
            ) from e

def validate_and_insert_data(table_data, expected_columns, db_name, table_name, db_columns):
    """
    Validate the table data and insert it into the database.

    :param table_data: The data to be inserted into the table.
    :type table_data: list
    :param expected_columns: The expected column names.
    :type expected_columns: list
    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    :raises ValidationError: If the column names do not match the expected columns.
    """
    validate_columns(table_data, expected_columns, db_name, table_name)
    
    # Create SQLite connection
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    insert_data(cursor, table_data, db_columns, table_name)
    
    # Commit changes and close the connection
    conn.commit()
    conn.close()

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
            time.sleep(0.4) # Trying to avoid hitting the quota
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

def authenticate_google_sheets(token_path="token.json", credentials_path="credentials.json"):
    """
    Authenticate with Google Sheets API and get the gspread client and credentials.

    :param token_path: The path to the token file, defaults to "token.json".
    :type token_path: str, optional
    :param credentials_path: The path to the credentials file, defaults to "credentials.json".
    :type credentials_path: str, optional
    :return: A tuple containing the gspread client and the Google API credentials.
    :rtype: tuple
    :raises RefreshError: If the Token has expired or been revoked.
    """
    creds = None

    # Load credentials from the token file if they exist
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # If there are no valid credentials available, prompt the user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # Delete the token file to force re-authentication
                os.remove('token.json')
                logger.critical("Token expired or revoked. Please re-run the script to authenticate.")
                raise
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    # Create a gspread client using the authenticated credentials
    client = gspread.authorize(creds)
    return client, creds

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

def clear_table(cursor, table_name):
    """
    Clear the data from the specified table and reset its auto-increment value.

    :param cursor: The SQLite cursor.
    :type cursor: sqlite3.Cursor
    :param table_name: The name of the table to be cleared.
    :type table_name: str
    """
    # Clear the existing table data
    clear_table_query = f"DELETE FROM {table_name}"
    cursor.execute(clear_table_query)
    # Reset the auto-increment value
    reset_autoincrement_query = f"UPDATE sqlite_sequence SET seq = 0 WHERE name = '{table_name}'"
    cursor.execute(reset_autoincrement_query)

def update_table(db_name, table_name, db_columns, fetch_function, fetch_args, expected_columns):
    """
    Update the specified table in the database with data fetched using the fetch_function.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    :param fetch_function: The function to fetch data from Google Sheets.
    :type fetch_function: function
    :param fetch_args: The arguments to be passed to the fetch_function.
    :type fetch_args: list
    :param expected_columns: The expected column names.
    :type expected_columns: list
    """
    try:
        # Initialize database and table if necessary
        initialize_database(db_name, table_name, db_columns)

        # Call the fetch function with arguments
        logging.info(f"Updating table {table_name} in database {db_name}...")
        table_data = fetch_function(*fetch_args)

        # Connect to the database
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Clear the existing table data and reset auto-increment
        clear_table(cursor, table_name)
        conn.commit()

        # Update the database
        validate_and_insert_data(table_data, expected_columns, db_name, table_name, db_columns)
        logger.info(f"Table {table_name} in database {db_name} updated.")
    except Exception as e:
        logger.critical(f"Failed to update table {table_name} in database {db_name}:\n{e}")
        raise

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
        table_data.append(sliced_row)

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
                table_data.append(row_data)
            row_data = []
            prev_row = cell.row
        row_data.append(cell.value)

    if any(row_data):  # Check the last row as well
        table_data.append(row_data)

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
    :param db_name: The name of the main database.
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

def process_character_worksheets(character_worksheet_list, character_tables):
    """
    Process and update the character worksheets.

    :param character_worksheet_list: A list of character worksheet objects.
    :type character_worksheet_list: list
    :param character_tables: A list of character table configurations.
    :type character_tables: list
    """
    for character_worksheet in character_worksheet_list:
        db_name = f"characters/{character_worksheet.title}.db"

        for table in character_tables:
            fetch_function_name = table["fetch_function"]
            fetch_function = globals()[fetch_function_name]
            fetch_args = replace_placeholders(table["fetch_args"], character_worksheet) # Evaluate the {character name} placeholder
            
            # Extremely cursed special case for Changli and Jiyan Resonance Chains
            if table["table_name"] == "ResonanceChain":
                if fetch_args[0].title == "Changli":
                    fetch_args = [fetch_args[0], "A30:K37"]
                if fetch_args[0].title == "Jiyan":
                    fetch_args = [fetch_args[0], "A29:K37"]

            update_table(
                db_name,
                table["table_name"],
                table["db_columns"],
                fetch_function,
                fetch_args,
                table["expected_columns"]
            )

def process_sheet_data_and_update_db(sheet, config_path, main_db_name, sheet_last_modified):
    """
    Process data from the Google Sheet and update the SQLite database.

    :param sheet: The Google Sheet object.
    :type sheet: gspread.Spreadsheet
    :param config_path: The path to the configuration file.
    :type config_path: str
    :param main_db_name: The name of the main database.
    :type main_db_name: str
    :param sheet_last_modified: The timestamp of the last modification of the Google Sheet.
    :type sheet_last_modified: datetime
    """
    # Find all character worksheets between "Rotation Samples" and "RotaSkills"
    worksheet_list = sheet.worksheets()
    character_worksheet_list = find_worksheet_range(worksheet_list, "Rotation Samples", "RotaSkills")

    # Load config
    config = load_config(config_path)

    # Collect all required worksheets from config
    required_worksheet_titles = collect_required_worksheets(config, main_db_name)
    required_worksheets = get_worksheets(sheet, required_worksheet_titles)

    # Update tables
    tables = config.get(main_db_name)["tables"]
    process_tables_from_config(main_db_name, tables, required_worksheets)

    # Process character worksheets
    character_tables = config.get("characters", {}).get("tables", [])
    process_character_worksheets(character_worksheet_list, character_tables)

    # Update the metadata (timestamp, version) at the very end
    latest_version = fetch_first_cell_of_last_row(sheet.worksheet("Version Log"), "A3")
    metadata = {
        "timestamp": sheet_last_modified,
        "version": latest_version
    }
    update_metadata(main_db_name, metadata)

    # Give a warning if Maygi has updated the latest spreadsheet version
    if latest_version != VERSION:
        logger.warning(f"Spreadsheet version ({latest_version}) does not match the script version ({VERSION}), expect things to break at any moment")

def update_sqlite_from_google_sheets(sheet_url, config_path="table_config.json", main_db_name="Calculator.db"):
    """
    Main function to import data from Google Sheets to SQLite.

    :param sheet_url: The URL of the Google Sheet.
    :type sheet_url: str
    :param config_path: The path to the configuration file.
    :type config_path: str
    :param main_db_name: The name of the main database.
    :type main_db_name: str
    """
    logger.info(f"{VERSION = }")
    
    # Authenticate and get both the client and credentials
    client, credentials = authenticate_google_sheets()

    # Open the Google Sheet
    sheet = retry_on_quota_exceeded(client.open_by_url, sheet_url)
    sheet_id = sheet_url.split("/")[5]

    # Get the last update timestamp from the Google Drive API
    sheet_last_modified_str = get_sheet_last_modified_time(sheet_id, credentials)
    sheet_last_modified = parse_sheet_last_modified(sheet_last_modified_str)

    # Ensure the metadata table exists to store the timestamp and version in
    create_metadata_table(main_db_name)

    # Check if updates are needed
    last_update_timestamp = get_last_update_timestamp(main_db_name)
    if last_update_timestamp is None or sheet_last_modified > last_update_timestamp:
        process_sheet_data_and_update_db(
            sheet, config_path, main_db_name, sheet_last_modified
        )
    else:
        logger.info("No updates needed.")

# Call to main function
update_sqlite_from_google_sheets(SHEET_URL)