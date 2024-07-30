"""
Database I/O
=====================================

by @HikariTenshi

This module handles the SQLite database operations. It includes functions to
initialize the database, access its data and update the database tables.
"""

import os
import sqlite3
import logging
from datetime import datetime

DB_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def create_metadata_table(db_name):
    """
    Create a metadata table in the database if it doesn't exist.

    :param db_name: The name of the database.
    :type db_name: str
    """
    conn = sqlite3.connect(db_name)
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

def get_last_update_timestamp(db_name):
    """
    Get the last update timestamp from the metadata table.

    :param db_name: The name of the database.
    :type db_name: str
    :return: The last update timestamp.
    :rtype: datetime or None
    """
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM metadata WHERE key = 'last_updated'")
    result = cursor.fetchone()
    conn.close()
    return datetime.strptime(result[0], DB_TIME_FORMAT) if result else None

def update_metadata(db_name, metadata):
    """
    Update the metadata table with the provided metadata.

    :param db_name: The name of the database.
    :type db_name: str
    :param metadata: The metadata to be updated (should include timestamp and version).
    :type metadata: dict
    """
    conn = sqlite3.connect(db_name)
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