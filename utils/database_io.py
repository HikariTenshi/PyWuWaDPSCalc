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
            f"{self.args[0]}\n"
            f"Expected values: {self.expected_values}\n"
            f"Given values:    {self.given_values}\n"
            f"Mismatches: {mismatches}\n"
            f"Excess in expected values: {excess_expected}\n"
            f"Excess in given values:    {excess_given}\n"
        )

def connect_to_database(db_name):
    """
    Establish a connection to the SQLite database.

    :param db_name: The name of the database.
    :type db_name: str
    :return: SQLite connection object.
    :rtype: sqlite3.Connection
    """
    return sqlite3.connect(db_name)

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

def ensure_directory_exists(db_name):
    """
    Ensure the directory for the database exists.

    :param db_name: The name of the database.
    :type db_name: str
    """
    directory = os.path.dirname(db_name)
    if not os.path.exists(directory) and directory != "":
        os.makedirs(directory)

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
    ensure_directory_exists(db_name)
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
    conn = connect_to_database(db_name)
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
        conn = connect_to_database(db_name)
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
    :type columns: str or list, optional
    :param where_clause: An optional SQL WHERE clause to filter the data.
    :type where_clause: str, optional
    :return: The fetched data as a list of tuples.
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
    :type columns1: str or list, optional
    :param columns2:
        The columns to fetch from the second table.
        If None, will select all columns except ID from this table.
        Use "" to select no columns.
    :type columns2: str or list, optional
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
        # logger.info(f'{query = }')
        data = execute_comparison_query(conn, query)
    except sqlite3.Error as e:
        logger.error(f"Failed to fetch data comparing tables from {db_name1} and {db_name2}: {e}")
        data = []
    finally:
        conn.close()
    
    return data

def overwrite_table_data(db_name, table_name, new_data, row_ids=None):
    """
    Overwrite the data in the specified table with new data.

    :param db_name: The name of the database.
    :type db_name: str
    :param table_name: The name of the table.
    :type table_name: str
    :param new_data: A list of dictionaries containing the new data to insert/update.
    :type new_data: list of dict
    :param row_ids: An optional list of row IDs to update. If None, the entire table is overwritten.
    :type row_ids: list of str or None
    """
    conn = connect_to_database(db_name)
    cursor = conn.cursor()
    
    try:
        if row_ids is None:
            # Clear the existing table data and reset auto-increment if no row IDs are provided
            clear_table(cursor, table_name)
            
            # Get the table columns
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns_info = cursor.fetchall()
            columns = [info[1] for info in columns_info if info[1] != "ID"]
            
            # Prepare the insert query for the whole table
            placeholders = ", ".join(["?"] * len(columns))
            insert_query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
            
            # Extract values from the new data (ignoring IDs)
            new_data_tuples = [tuple(row[col] for col in columns) for row in new_data]
            
            # Insert the new data
            cursor.executemany(insert_query, new_data_tuples)
        
        else:
            # If row IDs are provided, update only the specified rows
            for row_data, row_id in zip(new_data, row_ids):
                # Create a list of column=value pairs for the SET clause (excluding 'ID')
                set_clause = ", ".join([f"{col} = ?" for col in row_data.keys() if col != "ID"])
                
                # Check if there are columns to update
                if not set_clause:
                    continue

                # Prepare the update query
                update_query = f"UPDATE {table_name} SET {set_clause} WHERE ID = ?"
                values = [row_data[col] for col in row_data.keys() if col != "ID"]
                values.append(row_id)
                
                # Execute the update query
                cursor.execute(update_query, values)
        
        # Commit changes
        conn.commit()
        
        logger.info(f"Table {table_name} in database {db_name} has been updated successfully.")
    except Exception as e:
        logger.error(f"Failed to update data in table {table_name} in database {db_name}: {e}")
        raise
    finally:
        conn.close()