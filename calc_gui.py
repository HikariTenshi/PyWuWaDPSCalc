import logging
import os
import sys
import qdarkstyle
from qdarkstyle.dark.palette import DarkPalette
from qdarkstyle.light.palette import LightPalette
from PyQt5.QtWidgets import QMainWindow, QApplication, QTableWidget, QAction, QTabWidget, QWidget, QVBoxLayout, QScrollArea, QSizePolicy, QLabel, QGridLayout
from PyQt5.QtCore import QRect
from PyQt5 import uic
from utils.database_io import fetch_data_from_database
from utils.config_io import load_config
from custom_table_widget import CustomTableWidget

UI_FILE = "ui/calc_gui.ui"
CONSTANTS_DB_PATH = "databases/constants.db"
CALCULATOR_DB_PATH = "databases/calculator.db"
CONFIG_PATH = "databases/table_config.json"
CHARACTER_DATABASE_FOLDER_PATH = "databases/characters"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UI(QMainWindow):
    def __init__(self):
        super(UI, self).__init__()
        
        # Load the ui file
        uic.loadUi(UI_FILE, self)
        
        # Define the Widgets
        self.define_table_widgets()
        self.handle_menu_actions()
        self.create_character_tabs()
        
        self.load_all_table_widgets()
        
        # Show the App
        self.show()
    
    def define_table_widgets(self):
        config = load_config(CONFIG_PATH)
        constants_db_table_names = [table["table_name"] for table in config.get(CONSTANTS_DB_PATH)["tables"]]
        calculator_db_table_names = [table["table_name"] for table in config.get(CALCULATOR_DB_PATH)["tables"]]
        
        self.constants_db_table_column_collection = [(table["ui_columns"] if "ui_columns" in table else table["expected_columns"]) for table in config[CONSTANTS_DB_PATH]["tables"]]
        self.calculator_db_table_column_collection = [(table["ui_columns"] if "ui_columns" in table else table["expected_columns"]) for table in config[CALCULATOR_DB_PATH]["tables"]]
        self.characters_table_column_collection = [(table["ui_columns"] if "ui_columns" in table else table["expected_columns"]) for table in config["characters"]["tables"]]
        
        # Replace QTableWidget with CustomTableWidget
        self.constants_db_table_widgets = {
            name: self.findChild(CustomTableWidget, f'{camel_to_snake(name)}_table_widget')
            for name in constants_db_table_names}
        self.calculator_db_table_widgets = {
            name: self.findChild(CustomTableWidget, f'{camel_to_snake(name)}_table_widget')
            for name in calculator_db_table_names}
        self.character_table_widget_collection = {}
    
    def handle_menu_actions(self):
        self.action_light_theme = self.findChild(QAction, "action_light_theme")
        self.action_dark_theme = self.findChild(QAction, "action_dark_theme")
        
        self.action_light_theme.triggered.connect(lambda: toggle_stylesheet(LightPalette))
        self.action_dark_theme.triggered.connect(lambda: toggle_stylesheet(DarkPalette))
        
        self.action_reload_tables = self.findChild(QAction, "action_reload_tables")
        
        self.action_reload_tables.triggered.connect(self.load_all_table_widgets)

    def create_character_tabs(self):
        self.characters_tab_widget = self.findChild(QTabWidget, "characters_tab_widget")
        character_dbs = [f for f in os.listdir(CHARACTER_DATABASE_FOLDER_PATH) if f.endswith(".db")]

        for character_db in character_dbs:
            character_name = os.path.splitext(character_db)[0]
            character_camel_name = camel_to_snake(character_name)

            character_tab = self.create_character_tab(character_camel_name, character_db)
            scroll_area, scroll_area_widget_contents, scroll_area_grid_layout = self.create_scroll_area(character_camel_name)

            sections = ["Intro", "Outro", "InherentSkills", "ResonanceChains", "Skills"]
            for i, section in enumerate(sections):
                self.add_section(scroll_area_widget_contents, scroll_area_grid_layout, character_camel_name, character_name, character_db, section, i)

            scroll_area.setWidget(scroll_area_widget_contents)
            character_tab.layout().addWidget(scroll_area)
            self.characters_tab_widget.addTab(character_tab, character_name)

    def create_character_tab(self, character_camel_name, character_db):
        character_tab = QWidget()
        character_tab.setObjectName(f"{character_camel_name}_tab")
        character_tab_layout = QVBoxLayout(character_tab)
        character_tab_layout.setObjectName(f"{character_camel_name}_tab_layout")
        self.character_table_widget_collection[character_db] = {}
        return character_tab

    def create_scroll_area(self, character_camel_name):
        scroll_area = QScrollArea()
        scroll_area.setSizeAdjustPolicy(QScrollArea.AdjustToContents)
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName(f"{character_camel_name}_scroll_area")

        scroll_area_widget_contents = QWidget()
        scroll_area_widget_contents.setGeometry(QRect(0, 0, 108, 502))
        size_policy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        size_policy.setHeightForWidth(scroll_area_widget_contents.sizePolicy().hasHeightForWidth())
        scroll_area_widget_contents.setSizePolicy(size_policy)
        scroll_area_widget_contents.setObjectName(f"{character_camel_name}_scroll_area_widget_contents")

        scroll_area_grid_layout = QGridLayout(scroll_area_widget_contents)
        scroll_area_grid_layout.setObjectName(f"{character_camel_name}_scroll_area_grid_layout")

        return scroll_area, scroll_area_widget_contents, scroll_area_grid_layout

    def add_section(self, parent_widget, grid_layout, character_camel_name, character_name, character_db, section, row):
        section_vertical_layout = QVBoxLayout()
        section_vertical_layout.setObjectName(f"{character_camel_name}_{section.lower()}_vertical_layout")
        section_label = QLabel(parent_widget)
        section_label.setObjectName(f"{character_camel_name}_{section.lower()}_label")
        section_label.setText(f"{character_name}'s {section.replace('InherentSkills', 'Inherent Skills').replace('ResonanceChains', 'Resonance Chains')}")
        section_vertical_layout.addWidget(section_label)

        section_table_widget = CustomTableWidget(parent_widget)
        size_policy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        section_table_widget.setSizePolicy(size_policy)
        section_table_widget.setSizeAdjustPolicy(QTableWidget.AdjustToContents)
        section_table_widget.setObjectName(f"{character_camel_name}_{section.lower()}_table_widget")
        section_table_widget.setColumnCount(0)
        section_table_widget.setRowCount(0)
        section_vertical_layout.addWidget(section_table_widget)

        grid_layout.addLayout(section_vertical_layout, row, 0, 1, 1)

        self.character_table_widget_collection[character_db][section] = section_table_widget

    def configure_special_cases(self):
        # Settings table configurations
        if settings_table := self.calculator_db_table_widgets.get("Settings"):
            settings_table.checkbox_columns = [0]
            settings_table.dropdown_options = {
                1: fetch_data_from_database(CONSTANTS_DB_PATH, "WeaponMultipliers", columns="Level"),
                2: list(range(80, 130, 10)),
                4: fetch_data_from_database(CONSTANTS_DB_PATH, "SkillLevels", columns="Level"),
            }

        # CharacterLineup table configurations
        if character_lineup_table := self.calculator_db_table_widgets.get("CharacterLineup"):
            character_lineup_table.dropdown_options = {
                0: fetch_data_from_database(CONSTANTS_DB_PATH, "CharacterConstants", columns="Character"),
                1: list(range(7)),
                2: {}, # Will be dynamically updated based on character selection
                3: list(range(1, 6)),
                4: fetch_data_from_database(CONSTANTS_DB_PATH, "Echoes", columns="Echo", where_clause="Echo NOT LIKE '%(Swap)'"),
                5: fetch_data_from_database(CONSTANTS_DB_PATH, "EchoBuilds", columns="Build")
            }

        # RotationBuilder table configurations
        if rotation_builder_table := self.calculator_db_table_widgets.get("RotationBuilder"):
            rotation_builder_table.should_ensure_empty_row = True
            rotation_builder_table.dropdown_options = {
                0: [""] + fetch_data_from_database(CALCULATOR_DB_PATH, "CharacterLineup", columns="Character"),
                1: {} # Will be dynamically updated based on character selection
            }

    def load_table_widgets(self, table_widgets, column_name_collection, db_name):
        try:
            for i, (table_name, table_widget) in enumerate(table_widgets.items()):
                table_widget.setup_table(db_name, table_name, column_name_collection[i])
                table_widget.load_table_data()
        except Exception as e:
            print(e)

    def load_all_table_widgets(self):
        self.configure_special_cases()

        self.load_table_widgets(self.constants_db_table_widgets, self.constants_db_table_column_collection, CONSTANTS_DB_PATH)
        self.load_table_widgets(self.calculator_db_table_widgets, self.calculator_db_table_column_collection, CALCULATOR_DB_PATH)
        
        for character_db, character_table_widgets in self.character_table_widget_collection.items():
            self.load_table_widgets(character_table_widgets, self.characters_table_column_collection, f'{CHARACTER_DATABASE_FOLDER_PATH}/{character_db}')

def toggle_stylesheet(palette):
    # get the QApplication instance or crash if not set
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("No Qt Application found.")
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=palette))

def camel_to_snake(camel_str):
    if not camel_str:
        return ""
    
    # Replace spaces with underscores
    camel_str = camel_str.replace(" ", "_")
    
    snake_case = []
    for i, char in enumerate(camel_str):
        if char.isupper():
            if i > 0 and (camel_str[i-1].islower() or camel_str[i-1].isdigit()):
                snake_case.append("_")
            snake_case.append(char.lower())
        else:
            snake_case.append(char)
    
    return "".join(snake_case)

# Unsilence the silent crashes
sys._excepthook = sys.excepthook 
def exception_hook(exctype, value, traceback):
    print(exctype, value, traceback)
    sys._excepthook(exctype, value, traceback) 
    sys.exit(1) 
sys.excepthook = exception_hook 

# Initialize the App
app = QApplication(sys.argv)

# Apply Dark Theme
toggle_stylesheet(DarkPalette)

UIWindow = UI()
sys.exit(app.exec_())