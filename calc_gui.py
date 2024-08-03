from PyQt5.QtWidgets import QMainWindow, QApplication, QTableWidget, QTableWidgetItem, QAction, QHeaderView
from PyQt5.QtCore import QFile, QTextStream
from PyQt5 import uic
import sys
from utils.database_io import fetch_data_from_database
from utils.config_io import load_config

UI_FILE = "ui/calc_gui.ui"

DARK_THEME_PATH = "ui/themes/darkstyle.qss"
LIGHT_THEME_PATH = "ui/themes/lightstyle.qss"

CONSTANTS_DB_PATH = "databases/constants.db"
CALCULATOR_DB_PATH = "databases/calculator.db"
CONFIG_PATH = "databases/table_config.json"

class UI(QMainWindow):
    def __init__(self):
        super(UI, self).__init__()
        
        # Load the ui file
        uic.loadUi(UI_FILE, self)
        
        # Define the Widgets
        self.define_table_widgets()
        self.handle_menu_actions()
        
        self.load_all_table_widgets()
        
        # Show the App
        self.show()
    
    def define_table_widgets(self):
        config = load_config(CONFIG_PATH)
        constants_db_table_names = [table["table_name"] for table in config.get(CONSTANTS_DB_PATH)["tables"]]
        calculator_db_table_names = [table["table_name"] for table in config.get(CALCULATOR_DB_PATH)["tables"]]
        self.constants_db_table_column_collection = [(table["ui_columns"] if "ui_columns" in table else table["expected_columns"]) for table in config.get(CONSTANTS_DB_PATH)["tables"]]
        self.calculator_db_table_column_collection = [(table["ui_columns"] if "ui_columns" in table else table["expected_columns"]) for table in config.get(CALCULATOR_DB_PATH)["tables"]]
        
        self.constants_db_table_widgets = {
            name: self.findChild(QTableWidget, f'{camel_to_snake(name)}_table_widget')
            for name in constants_db_table_names}
        self.calculator_db_table_widgets = {
            name: self.findChild(QTableWidget, f'{camel_to_snake(name)}_table_widget')
            for name in calculator_db_table_names}
    
    def handle_menu_actions(self):
        self.action_light_theme = self.findChild(QAction, "action_light_theme")
        self.action_dark_theme = self.findChild(QAction, "action_dark_theme")
        
        self.action_light_theme.triggered.connect(lambda: toggle_stylesheet(LIGHT_THEME_PATH))
        self.action_dark_theme.triggered.connect(lambda: toggle_stylesheet(DARK_THEME_PATH))
        
        self.action_reload_tables = self.findChild(QAction, "action_reload_tables")
        
        self.action_reload_tables.triggered.connect(self.load_all_table_widgets)

    def load_table_data(self, table_widget, table_columns, db_name, table_name):
        table_widget.setRowCount(0)
        table_data = fetch_data_from_database(db_name, table_name)
        table_widget.setColumnCount(len(table_columns))
        table_widget.setHorizontalHeaderLabels(table_columns)
        
        for row_number, row_data in enumerate(table_data):
            table_widget.insertRow(row_number)
            for column_number, data in enumerate(row_data):
                table_widget.setItem(row_number, column_number, QTableWidgetItem(str(data)))
        
        # Resize columns to fit contents and enforce maximum size constraint
        for i in range(table_widget.columnCount()):
            table_widget.resizeColumnToContents(i)
            if table_widget.columnWidth(i) > 200:  # Adjust maximum width as needed
                table_widget.setColumnWidth(i, 200)
        
        # Set the resize mode to interactive after initial resizing
        header = table_widget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
    
    def load_table_widgets(self, table_widgets, table_column_collection, db_name):
        try:
            for i, (table_name, table_widget) in enumerate(table_widgets.items()):
                self.load_table_data(table_widget, table_column_collection[i], db_name, table_name)
        except Exception as e:
            print(e)
    
    def load_all_table_widgets(self):
        self.load_table_widgets(self.constants_db_table_widgets, self.constants_db_table_column_collection, CONSTANTS_DB_PATH)
        self.load_table_widgets(self.calculator_db_table_widgets, self.calculator_db_table_column_collection, CALCULATOR_DB_PATH)

def toggle_stylesheet(path):
    # get the QApplication instance or crash if not set
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("No Qt Application found.")

    file = QFile(path)
    file.open(QFile.ReadOnly | QFile.Text)
    stream = QTextStream(file)
    app.setStyleSheet(stream.readAll())

def camel_to_snake(camel_str):
    if not camel_str:
        return ""
    
    snake_case = []
    for char in camel_str:
        if char.isupper():
            if snake_case:  # Avoid adding an underscore at the beginning
                snake_case.append("_")
            snake_case.append(char.lower())
        else:
            snake_case.append(char)
    
    return "".join(snake_case)

# Initialize the App
app = QApplication(sys.argv)

# Apply Dark Theme
toggle_stylesheet(DARK_THEME_PATH)

UIWindow = UI()
sys.exit(app.exec_())