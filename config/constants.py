"""
Constants
=========

This module contains constants and logging configuration used across the application.

Constants
---------
- **VERSION**: The current version of the application.
- **CONSTANTS_DB_PATH**: Path to the constants database file.
- **CHARACTERS_DB_PATH**: Path to the characters database folder.
- **CALCULATOR_DB_PATH**: Path to the calculator database file.
- **CONFIG_PATH**: Path to the table configuration JSON file.
- **UI_FILE**: Path to the UI file.
- **CREDENTIALS_PATH**: Path to the credentials JSON file.
- **TOKEN_PATH**: Path to the token JSON file.
- **SHEET_URL**: URL of the Google Sheets document.
- **SCOPES**: List of OAuth 2.0 scopes for Google Sheets and Drive API.
- **SHEET_TIME_FORMAT**: Time format used in the Google Sheets.
- **DB_TIME_FORMAT**: Time format used in the database.

Logging Configuration
---------------------
This module configures the logging for the application.

- **logger**: A logger instance named after this module.

Example Usage:

    import logging
    from config.constants import logger

    # This ensures that the correct module name shows up
    logger = logging.getLogger(__name__)

    def some_function():
        logger.info("This is an informational message.")
"""

import logging

VERSION = "V3.3.3"
CONSTANTS_DB_PATH = "databases/constants.db"
CHARACTERS_DB_PATH = "databases/characters"
CALCULATOR_DB_PATH = "databases/calculator.db"
CONFIG_PATH = "config/table_config.json"
UI_FILE = "ui/calc_gui.ui"
CREDENTIALS_PATH = "credentials/credentials.json"
TOKEN_PATH = "credentials/token.json"
SHEET_URL="https://docs.google.com/spreadsheets/d/1vTbG2HfkVxyqvNXF2taikStK-vJJf40QrWa06Fgj17c/edit#gid=0"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.metadata.readonly"]
SHEET_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DB_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)