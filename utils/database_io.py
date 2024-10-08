"""
Database I/O
============

by @HikariTenshi

This module handles the SQLite database operations. It includes functions to
initialize the database, access its data and update the database tables.
"""


import contextlib
import os
import sqlite3
import logging
from datetime import datetime
from config.constants import logger, DB_TIME_FORMAT

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
            f"{self.args[0]}\n"
            f"Expected values: {self.expected_values}\n"
            f"Given values:    {self.given_values}\n"
            f"Mismatches: {mismatches}\n"
            f"Excess in expected values: {excess_expected}\n"
            f"Excess in given values:    {excess_given}\n"
        )

def table_exists(db_name, table_name):
    """
    Check if a specific table exists in the SQLite database.
    Returns False if the database does not exist.

    :param db_name: The name of the database file.
    :type db_name: str
    :param table_name: The name of the table to check.
    :type table_name: str
    :return: Whether the table exists in the database.
    :rtype: bool
    """
    # Check if the database file exists
    if not os.path.exists(db_name):
        logger.debug(f"The database '{db_name}' does not exist.")
        return False
    
    # Connect to the database and check for the table
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';")
        table_exists = cursor.fetchone() is not None
        conn.close()
        return table_exists
    except sqlite3.Error as e:
        logger.error(f"An error occurred while checking for table '{table_name}': {e}")
        return False

def ensure_directory_exists(db_name):
    """
    Ensure the directory for the database exists.

    :param db_name: The name of the database.
    :type db_name: str
    """
    directory = os.path.dirname(db_name)
    if not os.path.exists(directory) and directory != "":
        os.makedirs(directory)

def connect_to_database(db_name):
    """
    Establish a connection to the SQLite database.

    :param db_name: The name of the database.
    :type db_name: str
    :return: SQLite connection object.
    :rtype: sqlite3.Connection
    """
    try:
        ensure_directory_exists(db_name)
        return sqlite3.connect(db_name)
    except sqlite3.Error as e:
        logger.critical(f"Failed to connect to the database {db_name}: {e}")
        raise

def create_metadata_table(db_name):
    """
    Create a metadata table in the database if it doesn't exist.

    :param db_name: The name of the database.
    :type db_name: str
    """
    conn = connect_to_database(db_name)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    conn.commit()
    conn.close()

def create_table(conn, table_name, db_columns):
    """
    Create a table in the database with the specified columns.

    :param conn: The SQLite connection object.
    :type conn: sqlite3.Connection
    :param table_name: The name of the table.
    :type table_name: str
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    """
    cursor = conn.cursor()
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        ID INTEGER PRIMARY KEY AUTOINCREMENT,
        {', '.join([f'{col} {dtype}' for col, dtype in db_columns.items()])}
    )
    """
    cursor.execute(create_table_query)

def table_is_empty(conn, table_name):
    """
    Check if a table in the database is empty.

    :param conn: The SQLite connection object.
    :type conn: sqlite3.Connection
    :param table_name: The name of the table.
    :type table_name: str
    :return: True if the table is empty, False otherwise.
    :rtype: bool
    """
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    row_count = cursor.fetchone()[0]
    return row_count == 0

def insert_initial_data(conn, table_name, db_columns, initial_data):
    """
    Insert initial data into a table if it is empty.

    :param conn: The SQLite connection object.
    :type conn: sqlite3.Connection
    :param table_name: The name of the table.
    :type table_name: str
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    :param initial_data: A list of tuples containing the initial data to insert.
    :type initial_data: list of tuples
    """
    if initial_data and table_is_empty(conn, table_name):
        columns = ", ".join(db_columns.keys())
        placeholders = ", ".join(["?"] * len(db_columns))
        insert_query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        cursor = conn.cursor()
        cursor.executemany(insert_query, initial_data)

def initialize_database(db_name, table_name, db_columns, initial_data=None):
    """
    Initialize the database, create the specified table with the given columns
    and optionally insert initial data if the table is empty.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    :param initial_data: 
        Optional initial data to insert into the table.
        Should be a list of tuples, where each tuple corresponds
        to a row of data.
    :type initial_data: list of tuples, optional
    """
    conn = connect_to_database(db_name)

    try:
        create_table(conn, table_name, db_columns)
        insert_initial_data(conn, table_name, db_columns, initial_data)
        conn.commit()
    finally:
        conn.close()

def get_last_update_timestamp(db_name):
    """
    Get the last update timestamp from the metadata table.

    :param db_name: The name of the database.
    :type db_name: str
    :return: The last update timestamp.
    :rtype: datetime or None
    """
    conn = connect_to_database(db_name)
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
    conn = connect_to_database(db_name)
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
    for row in table_data:
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

def insert_data_with_labels(cursor, table_data, db_columns, table_name):
    """
    Insert data into the database table. This removes the first row which is assumed to be the lables.

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
    insert_data(cursor, table_data[1:], db_columns, table_name)

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
    conn = connect_to_database(db_name)
    cursor = conn.cursor()
    
    insert_data_with_labels(cursor, table_data, db_columns, table_name)
    
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

def clear_and_initialize_table(db_name, table_name, db_columns, initial_data=None):

    """
    Clear the specified table, then initialize it with the given columns
    and optionally insert initial data if the table is empty.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    :param initial_data: 
        Optional initial data to insert into the table.
        Should be a list of tuples, where each tuple corresponds
        to a row of data.
    :type initial_data: list of tuples, optional
    """
    # Connect to the database
    conn = connect_to_database(db_name)
    cursor = conn.cursor()
    
    # If the OperationalError occurs, it means that the table doesn't exist and therefore doesn't need to be cleared
    with contextlib.suppress(sqlite3.OperationalError):
        # Clear the existing table data and reset auto-increment
        clear_table(cursor, table_name)
        conn.commit()

    # Initialize the table
    initialize_database(db_name, table_name, db_columns, initial_data)

def update_table_using_fetch_function(db_name, table_name, db_columns, fetch_function, fetch_args, expected_columns):
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
        logger.debug(f"Updating table {table_name} in database {db_name}...")
        table_data = fetch_function(*fetch_args)

        # Connect to the database
        conn = connect_to_database(db_name)
        cursor = conn.cursor()

        # Clear the existing table data and reset auto-increment
        clear_table(cursor, table_name)
        conn.commit()

        # Update the database
        validate_and_insert_data(table_data, expected_columns, db_name, table_name, db_columns)
        logger.debug(f"Table {table_name} in database {db_name} updated.")
    except Exception as e:
        logger.critical(f"Failed to update table {table_name} in database {db_name}:\n{e}")
        raise

def determine_columns_to_fetch(cursor, table_name, columns):
    """
    Determine which columns to fetch from the database.

    :param cursor: SQLite cursor object.
    :type cursor: sqlite3.Cursor
    :param table_name: The name of the table.
    :type table_name: str
    :param columns: The columns to fetch or None to fetch all columns except "ID".
    :type columns: str, list or None
    :return: A comma-separated string of columns to fetch or None.
    :rtype: str or None
    """
    if columns is None:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [info[1] for info in cursor.fetchall() if info[1].lower() != "id"]
    elif isinstance(columns, list):
        columns = [col for col in columns if col]
    elif isinstance(columns, str):
        columns = [columns]
    return ", ".join(columns)

def build_query(table_name, columns, where_clause):
    """
    Build the SQL SELECT query.

    :param table_name: The name of the table.
    :type table_name: str
    :param columns: The columns to fetch.
    :type columns: str
    :param where_clause: An optional SQL WHERE clause.
    :type where_clause: str, optional
    :return: The SQL query string.
    :rtype: str
    :raises ValueError: If columns is None.
    """
    # Handle None value for columns
    if columns is None:
        raise ValueError("'columns' must be provided and can't be None.")
    
    query = f"SELECT {columns} FROM {table_name}"
    if where_clause:
        query += f" WHERE {where_clause}"
    return query

def execute_query(cursor, query):
    """
    Execute the SQL query and fetch all results.

    :param cursor: SQLite cursor object.
    :type cursor: sqlite3.Cursor
    :param query: The SQL query string to execute.
    :type query: str
    :return: The fetched data as a list of tuples.
    :rtype: list
    """
    cursor.execute(query)
    return cursor.fetchall()

def fetch_data_from_database(db_name, table_name, columns=None, where_clause=None):
    """
    Fetch specified data from a database table or return all rows if unspecified.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param columns: The columns to fetch, defaults to all columns except ID.
    :type columns: str or list of str, optional
    :param where_clause: An optional SQL WHERE clause to filter the data.
    :type where_clause: str, optional
    :return: The fetched data as a list of tuples or a list of values if only one column is requested.
    :rtype: list
    """
    conn = connect_to_database(db_name)
    cursor = conn.cursor()
    
    columns_to_fetch = determine_columns_to_fetch(cursor, table_name, columns)
    query = build_query(table_name, columns_to_fetch, where_clause)
    
    try:
        data = execute_query(cursor, query)
        if isinstance(columns, str):
            columns = [columns]

        # Handle the case where only one column is requested in total
        if columns is not None and len(columns) == 1:
            data = [row[0] for row in data]
    except sqlite3.Error as e:
        logger.error(f"Failed to fetch data from table {table_name} in database {db_name}: {e}")
        data = []
    finally:
        conn.close()

    return data

def attach_second_database(conn, alias, db_name):
    """
    Attach a second database to the current connection using an alias.

    :param conn: The SQLite connection object for the first database.
    :type conn: sqlite3.Connection
    :param alias: The alias for the attached database.
    :type alias: str
    :param db_name: The path to the second database.
    :type db_name: str
    """
    attach_query = f"ATTACH DATABASE '{db_name}' AS {alias}"
    with conn:
        conn.execute(attach_query)

def build_comparison_query(table_name1, columns1, table_name2, columns2, where_clause):
    """
    Build the SQL SELECT query to compare data from two tables in different databases.

    :param table_name1: The name of the first table.
    :type table_name1: str
    :param columns1: The columns to fetch from the first table.
    :type columns1: str
    :param table_name2: The name of the second table.
    :type table_name2: str
    :param columns2: The columns to fetch from the second table.
    :type columns2: str
    :param where_clause: The SQL WHERE clause to compare values between the two tables.
    :type where_clause: str
    :return: The SQL query string for comparison.
    :rtype: str
    :raises ValueError: If both columns1 and columns2 are None.
    """
    # Handle None values for columns1 and columns2
    if columns1 is None and columns2 is None:
        raise ValueError("At least one of columns1 or columns2 must be provided.")

    # Prepare the SELECT clause
    select_clause = ""
    if columns1:
        select_clause += f't1.{columns1}'
        if columns2:
            select_clause += ", "
    if columns2:
        select_clause += f't2.{columns2}'

    # Build the final SQL query
    return f"""
    SELECT {select_clause}
    FROM {table_name1} AS t1
    JOIN {table_name2} AS t2 ON {where_clause}
    """

def execute_comparison_query(conn, query):
    """
    Execute the SQL query comparing values between two tables and fetch results.

    :param conn: SQLite connection object for the first database.
    :type conn: sqlite3.Connection
    :param query: The SQL query string to execute.
    :type query: str
    :return: The fetched data as a list of tuples.
    :rtype: list
    """
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchall()

def check_table_exists(db_name, table_name):
    """
    Check if a table exists in the specified database.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table to check.
    :type table_name: str
    :return: True if the table exists, False otherwise.
    :rtype: bool
    """
    conn = connect_to_database(db_name)
    cursor = conn.cursor()

    try:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';")
        exists = cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Error checking table existence in {db_name}: {e}")
        exists = False
    finally:
        conn.close()

    return exists

def amount_of_items(var):
    """
    Returns the amount of items a given variable holds.
    
    This function may work for other types of variables but it was only written with 
    None, str and list in mind. Empty str counts as 0.
    
    :param var: The variable to count the items for.
    :type var: None, str, list
    :return: The amount of items the variable holds.
    :rtype: int
    """
    if var is None:
        return 0
    if isinstance(var, str):
        return 0 if var == "" else 1
    return len(var)

def fetch_data_comparing_two_databases(db_name1, table_name1, db_name2, table_name2, columns1=None, columns2=None, where_clause=None):
    """
    Fetch data from two distinct databases by comparing values based on a WHERE clause.
    
    :param db_name1: The name of the first database.
    :type db_name1: str
    :param table_name1: The name of the table in the first database.
    :type table_name1: str
    :param db_name2: The name of the second database.
    :type db_name2: str
    :param table_name2: The name of the table in the second database.
    :type table_name2: str
    :param columns1:
        The columns to fetch from the first table.
        If None, will select all columns except ID from this table.
        Use "" to select no columns.
    :type columns1: str or list of str, optional
    :param columns2:
        The columns to fetch from the second table.
        If None, will select all columns except ID from this table.
        Use "" to select no columns.
    :type columns2: str or list of str, optional
    :param where_clause: The SQL WHERE clause to compare values between the two tables.
    :type where_clause: str
    :return: The fetched data as a list of tuples.
    :rtype: list
    """
    # Check if both tables exist
    if not check_table_exists(db_name1, table_name1):
        logger.error(f"Table {table_name1} does not exist in {db_name1}")
        return []
    if not check_table_exists(db_name2, table_name2):
        logger.error(f"Table {table_name2} does not exist in {db_name2}")
        return []
    
    conn = connect_to_database(db_name1)
    try:
        attach_second_database(conn, 'db2', db_name2)
        columns1_to_fetch = determine_columns_to_fetch(conn.cursor(), table_name1, columns1)
        columns2_to_fetch = determine_columns_to_fetch(conn.cursor(), table_name2, columns2)

        query = build_comparison_query(table_name1, columns1_to_fetch, f'db2.{table_name2}', columns2_to_fetch, where_clause)
        data = execute_comparison_query(conn, query)

        # Handle the case where only one column is requested in total
        total_columns = amount_of_items(columns1) + amount_of_items(columns2)
        if total_columns == 1:
            data = [row[0] for row in data]
    except sqlite3.Error as e:
        logger.error(f"Failed to fetch data comparing tables from {db_name1} and {db_name2}: {e}")
        data = []
    finally:
        conn.close()
    
    return data

def overwrite_table_data(db_name, table_name, db_columns, table_data):
    """
    Overwrite the data in the specified table with new data.
    This clears any existing data in that table.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param db_columns: A dictionary of column names and their data types.
    :type db_columns: dict
    :param table_data: The table data to be inserted.
    :type table_data: list
    """
    try:
        # Initialize database and table if necessary
        initialize_database(db_name, table_name, db_columns)

        # Connect to the database
        conn = connect_to_database(db_name)
        cursor = conn.cursor()

        # Clear the existing table data and reset auto-increment
        clear_table(cursor, table_name)
        conn.commit()

        # Update the database
        insert_data(cursor, table_data, db_columns, table_name)
        conn.commit()
        logger.debug(f"Table {table_name} in database {db_name} has been updated successfully.")
    except Exception as e:
        logger.critical(f"Failed to update data in table {table_name} in database {db_name}:\n{e}")
        raise
    finally:
        conn.close()

def overwrite_table_data_by_columns(db_name, table_name, columns, new_data):
    """
    Overwrite specific columns in a table with new data. If there are more rows in new_data than in the table,
    new rows will be inserted.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table to update.
    :type table_name: str
    :param columns: The list of column names to be updated.
    :type columns: str or list of str
    :param new_data: The new data to insert into the specified columns.
    :type new_data: list of tuples, list of lists, or list of values if single column
    :raises ValueError: If the number of columns does not match the data.
    """
    if not new_data or not columns:
        raise ValueError("Both 'new_data' and 'column_names' must be provided and cannot be empty.")
    
    # Connect to the database
    conn = connect_to_database(db_name)
    cursor = conn.cursor()

    # Validate the table columns
    cursor.execute(f"PRAGMA table_info({table_name})")
    table_info = cursor.fetchall()
    table_columns = [info[1] for info in table_info]
    
    if isinstance(columns, str):
        columns = [columns]

    for col in columns:
        if col not in table_columns:
            raise ValueError(f"Column '{col}' does not exist in table '{table_name}'.")

    # Get the current row count of the table
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    row_count = cursor.fetchone()[0]

    # Ensure new_data is in the correct format
    if len(columns) == 1:
        # If there's only one column, each item in new_data should be a single value
        new_data = [(value,) for value in new_data]
    else:
        # If multiple columns, convert list of lists to list of tuples if needed
        new_data = [tuple(row) if isinstance(row, list) else row for row in new_data]

    # Split new_data into existing rows (for updating) and new rows (for inserting)
    existing_rows_data = new_data[:row_count]
    new_rows_data = new_data[row_count:]

    # Prepare the SQL update statement for existing rows
    update_columns = ", ".join([f"{col} = ?" for col in columns])
    update_query = f"UPDATE {table_name} SET {update_columns} WHERE ID = ?"

    # Update existing rows
    for row_id, row_data in enumerate(existing_rows_data, start=1):
        if len(row_data) != len(columns):
            raise ValueError(f"Row data length {len(row_data)} does not match the number of columns {len(columns)}.")
        
        cursor.execute(update_query, (*row_data, row_id))
    
    # Prepare the SQL insert statement for new rows
    if new_rows_data:
        insert_columns = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        insert_query = f"INSERT INTO {table_name} ({insert_columns}) VALUES ({placeholders})"

        # Insert new rows
        cursor.executemany(insert_query, new_rows_data)

    # Commit changes and close the connection
    conn.commit()
    conn.close()

    logger.debug(f"Columns {columns} in table {table_name} of database {db_name} have been successfully overwritten.")

def overwrite_table_data_by_row_ids(db_name, table_name, new_data):
    """
    Overwrite the data in the specified table with new data.
    Update existing rows or insert new rows based on row IDs.

    The function updates the rows in the table where the provided row IDs match,
    and inserts new rows if the row IDs do not already exist in the table. Only the
    columns provided in the new data dictionaries will be updated or inserted; 
    other columns in the table will remain unchanged during updates.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param new_data: A list of dictionaries containing the new data to insert/update.
                    Each dictionary must include an "ID" key for identifying rows.
    :type new_data: list of dict
    
    Suppose we have a table called `users` in a SQLite database `app.db` with columns `ID`, `name`, and `age`.
    We want to update the name for user with ID `1` and insert a new user with ID `3`.

    Usage Example:

        new_data = [
            {"ID": 1, "name": "John Doe"}, # This will update the name for the user with ID 1
            {"ID": 3, "name": "Jane Smith", "age": 30} # This will insert a new row with ID 3
        ]

        overwrite_table_data_by_row_ids("app.db", "users", new_data)

    After executing this function, the `users` table will have the updated name for the user with ID `1`,
    and a new row with ID `3` and the provided `name` and `age` values.
    """
    conn = connect_to_database(db_name)
    cursor = conn.cursor()

    try:
        # Extract columns from the keys of the first dictionary in new_data
        columns = list(new_data[0].keys())

        # Extract row IDs from new_data
        row_ids = [row["ID"] for row in new_data]

        # Fetch existing IDs from the table
        cursor.execute(f"SELECT ID FROM {table_name} WHERE ID IN ({', '.join(['?'] * len(row_ids))})", row_ids)
        existing_ids = {row[0] for row in cursor.fetchall()}
        ids_to_insert = set(row_ids) - existing_ids

        # Update existing rows
        for row_data, row_id in zip(new_data, row_ids):
            if row_id in existing_ids:
                # Create a list of column=value pairs for the SET clause (excluding 'ID')
                set_clause = ", ".join([f"{col} = ?" for col in row_data.keys() if col != "ID"])

                # Prepare the update query
                update_query = f"UPDATE {table_name} SET {set_clause} WHERE ID = ?"
                values = [row_data[col] for col in row_data.keys() if col != "ID"]
                values.append(row_id)

                # Execute the update query
                cursor.execute(update_query, values)

        # Insert new rows
        for row_data in new_data:
            if row_data["ID"] in ids_to_insert:
                # Prepare the insert query including the ID
                placeholders = ", ".join(["?"] * len(columns))
                insert_query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

                # Insert the new row
                values = [row_data[col] for col in columns]
                cursor.execute(insert_query, values)

        # Commit changes
        conn.commit()

        logger.debug(f"Table {table_name} in database {db_name} has been updated successfully.")
    except Exception as e:
        logger.error(f"Failed to update data in table {table_name} in database {db_name}: {e}")
        raise
    finally:
        conn.close()

def set_unspecified_columns_to_null(db_name, table_name, specified_columns, where_clause=None):
    """
    Set all values of columns that are not specified to NULL in a table, except for the 'ID' column.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param specified_columns: The list of columns that should not be set to NULL.
    :type specified_columns: list of str
    :param where_clause: An optional SQL WHERE clause to filter the rows to update.
    :type where_clause: str, optional
    """
    conn = connect_to_database(db_name)
    cursor = conn.cursor()

    # Retrieve the column names from the table schema
    cursor.execute(f"PRAGMA table_info({table_name})")
    all_columns = [info[1] for info in cursor.fetchall()]

    # Ignore the "ID" column which is assumed to be the auto-increment primary key
    if "ID" in all_columns:
        all_columns.remove("ID")

    # Identify columns to be set to NULL
    columns_to_null = [col for col in all_columns if col not in specified_columns]
    
    if not columns_to_null:
        logger.debug(f"No columns to set to NULL in table {table_name}.")
        conn.close()
        return
    
    # Build the SQL UPDATE query
    set_clause = ", ".join([f"{col} = NULL" for col in columns_to_null])
    update_query = f"UPDATE {table_name} SET {set_clause}"
    
    if where_clause:
        update_query += f" WHERE {where_clause}"

    try:
        cursor.execute(update_query)
        conn.commit()
        logger.debug(f"Columns {columns_to_null} in table {table_name} have been set to NULL.")
    except sqlite3.Error as e:
        logger.error(f"Failed to set unspecified columns to NULL in table {table_name}: {e}")
    finally:
        conn.close()

def append_rows_to_table(db_name, table_name, columns=None, new_data=None):
    """
    Append rows of data to the specified table in the database.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table to append data to.
    :type table_name: str
    :param columns: The list of column names to insert data into. 
                    If None, inserts into all columns except 'ID'.
    :type columns: str or list of str, optional
    :param new_data: The new data to append as rows.
    :type new_data: list of tuples, list of lists, or list of values if single column
    :raises ValueError: If columns are invalid or data doesn't match the columns.
    """

    if not new_data:
        raise ValueError("Parameter 'new_data' must be provided and cannot be empty.")

    # Connect to the database
    conn = connect_to_database(db_name)
    cursor = conn.cursor()

    # Retrieve table columns
    cursor.execute(f"PRAGMA table_info({table_name})")
    table_info = cursor.fetchall()
    table_columns = [info[1] for info in table_info]

    # Determine columns to insert into
    if columns is None:
        # Insert into all columns except 'ID'
        columns_to_insert = [col for col in table_columns if col.lower() != "id"]
    else:
        # Normalize 'columns' to a list
        if isinstance(columns, str):
            columns = [columns]
        elif isinstance(columns, list):
            if not all(isinstance(col, str) for col in columns):
                conn.close()
                raise ValueError("All column names must be strings.")
        else:
            conn.close()
            raise ValueError("Parameter 'columns' must be a string, list of strings, or None.")

        columns_to_insert = columns

    # Format 'new_data' appropriately
    if len(columns_to_insert) == 1:
        # Single column: 'new_data' can be a list of values, tuples, or lists
        formatted_new_data = []
        for item in new_data:
            if isinstance(item, (list, tuple)):
                if len(item) != 1:
                    conn.close()
                    raise ValueError(f"Each row must have exactly one value for single-column insert. Found: {item}")
                formatted_new_data.append(tuple(item))
            else:
                # Single value: wrap it in a tuple
                formatted_new_data.append((item,))
    else:
        # Multiple columns: 'new_data' should be a list of tuples/lists matching the number of columns
        formatted_new_data = []
        for item in new_data:
            if isinstance(item, (list, tuple)):
                if len(item) != len(columns_to_insert):
                    conn.close()
                    raise ValueError(
                        f"Row data length {len(item)} does not match the number of columns {len(columns_to_insert)}."
                    )
                formatted_new_data.append(tuple(item))
            else:
                conn.close()
                raise ValueError(
                    f"Each row in 'new_data' must be a list or tuple matching the columns. Found: {item}"
                )

    # Prepare the SQL INSERT statement
    placeholders = ", ".join(["?"] * len(columns_to_insert))
    insert_columns = ", ".join(columns_to_insert)
    insert_query = f"INSERT INTO {table_name} ({insert_columns}) VALUES ({placeholders})"

    # Execute the INSERT statement using executemany for efficiency
    try:
        cursor.executemany(insert_query, formatted_new_data)
    except sqlite3.Error as e:
        conn.close()
        logger.error(f"Failed to insert data into table '{table_name}' in database '{db_name}': {e}")
        raise

    # Commit the transaction and close the connection
    conn.commit()
    conn.close()

    logger.debug(
        f"Appended {len(formatted_new_data)} row(s) to table '{table_name}' in database '{db_name}'."
    )