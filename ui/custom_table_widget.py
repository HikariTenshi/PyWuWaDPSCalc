import logging
import traceback
from PyQt5.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QMenu, QAction, QUndoStack, QHeaderView
from PyQt5.QtGui import QKeySequence, QColor, QBrush, QFont
from PyQt5.QtCore import Qt
from utils.database_io import fetch_data_from_database, fetch_data_comparing_two_databases, overwrite_table_data_by_row_ids
from utils.config_io import load_config
from utils.function_call_stack import FunctionCallStack
from config.constants import logger, CONSTANTS_DB_PATH, CHARACTERS_DB_PATH, CONFIG_PATH, CALCULATOR_DB_PATH
from ui.custom_combo_box import CustomComboBox
from ui.check_box_item import CheckBoxItem
from ui.paste_command import PasteCommand

logger = logging.getLogger(__name__)

class CustomTableWidget(QTableWidget):
    def __init__(self, parent=None):
        try:
            super(CustomTableWidget, self).__init__(parent)

            self.setContextMenuPolicy(Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self.show_context_menu)

            # Initialize Undo/Redo stack
            self.undo_stack = QUndoStack(self)

            # Add shortcuts for copy/paste and undo/redo
            self.copy_action = QAction("Copy", self)
            self.paste_action = QAction("Paste", self)
            self.undo_action = QAction("Undo", self)
            self.redo_action = QAction("Redo", self)

            self.copy_action.setShortcut(QKeySequence("Ctrl+C"))
            self.paste_action.setShortcut(QKeySequence("Ctrl+V"))
            self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
            self.redo_action.setShortcut(QKeySequence("Ctrl+Y"))

            self.copy_action.triggered.connect(self.copy_selection)
            self.paste_action.triggered.connect(self.paste_selection)
            self.undo_action.triggered.connect(self.undo_stack.undo)
            self.redo_action.triggered.connect(self.undo_stack.redo)

            self.addAction(self.copy_action)
            self.addAction(self.paste_action)
            self.addAction(self.undo_action)
            self.addAction(self.redo_action)

            self.copy_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.paste_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.undo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            self.redo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)

            self.copy_action.setEnabled(True)
            self.paste_action.setEnabled(True)
            self.undo_action.setEnabled(True)
            self.redo_action.setEnabled(True)

            # Dictionary to store dropdown options
            self.dropdown_options = {}

            # Flag to determine if an empty row should be maintained
            self.should_ensure_empty_row = False
            
            # List of columns that should use checkboxes
            self.checkbox_columns = []

            # Connect cell changed signal
            self.cellChanged.connect(self.on_cell_changed)

            self.call_stack = FunctionCallStack()
        except Exception as e:
            logger.error(f'Failed to init the CustomTableWidget\n{get_trace(e)}')

    def update_dropdown_value_from_database(self, row, column, dropdown):
        try:
            with self.call_stack.track_function():
                where_clause = f'ID = {row + 1}'
                current_value_list = fetch_data_from_database(self.db_name, self.table_name, columns=self.db_columns[column], where_clause=where_clause)
                current_value = str(current_value_list[0]) if current_value_list else ""
                logger.info(f'Updating dropdown at row {row}, column {column} in table {self.table_name} to value: {current_value}')
                dropdown.setCurrentText(current_value)
        except Exception as e:
            logger.error(f'Failed to update dropdown value from database\n{get_trace(e)}')

    def apply_dropdowns(self):
        try:
            with self.call_stack.track_function():
                for column_index, options in self.dropdown_options.items():
                    # Check if options is a dictionary (dependent on character)
                    if isinstance(options, dict):
                        # Iterate through each row to apply the correct options
                        for row in range(self.rowCount()):
                            # Get the character value from the character column (assuming character column is index 0)
                            if character_item := self.item(row, 0):
                                character = character_item.text()
                            else:
                                character = self.cellWidget(row, 0).currentText() if self.cellWidget(row, 0) else ""

                            # Determine the appropriate options for this row
                            row_options = options.get(character, [])
                            row_options = [str(option) for option in row_options]
                            
                            # Apply the options to the dropdown in the current row and column
                            dropdown = self.cellWidget(row, column_index)
                            if dropdown is not None:
                                current_value = dropdown.currentText()
                                dropdown.clear()
                                dropdown.addItems(row_options)
                                dropdown.setCurrentText(current_value or "")
                            else:
                                dropdown = CustomComboBox()
                                dropdown.addItems(row_options)
                                dropdown.currentIndexChanged.connect(lambda _, r=row, c=column_index: self.on_dropdown_changed(r, c))
                                self.setCellWidget(row, column_index, dropdown)
                            self.update_dropdown_value_from_database(row, column_index, dropdown)
                    else:
                        # If options is not a dictionary, apply as usual
                        options = [str(option) for option in options]
                        for row in range(self.rowCount()):
                            dropdown = self.cellWidget(row, column_index)
                            if dropdown is not None:
                                current_value = dropdown.currentText()
                                dropdown.clear()
                                dropdown.addItems(options)
                                dropdown.setCurrentText(current_value or "")
                            else:
                                dropdown = CustomComboBox()
                                dropdown.addItems(options)
                                dropdown.currentIndexChanged.connect(lambda _, r=row, c=column_index: self.on_dropdown_changed(r, c))
                                self.setCellWidget(row, column_index, dropdown)
                            self.update_dropdown_value_from_database(row, column_index, dropdown)
        except Exception as e:
            logger.error(f'Failed to apply dropdowns\n{get_trace(e)}')

    def add_dropdown_to_column(self, column_index, items):
        try:
            with self.call_stack.track_function():
                items = [str(item) for item in items]
                for row in range(self.rowCount()):
                    dropdown = self.cellWidget(row, column_index)
                    if dropdown is None:
                        dropdown = CustomComboBox()
                        dropdown.addItems(items)
                        dropdown.currentIndexChanged.connect(lambda _, r=row, c=column_index: self.on_dropdown_changed(r, c))
                        self.setCellWidget(row, column_index, dropdown)
                    else:
                        current_value = dropdown.currentText()
                        dropdown.clear()
                        dropdown.addItems(items)
                        dropdown.setCurrentText(current_value or "")
        except Exception as e:
            logger.error(f'Failed to add dropdown\n{get_trace(e)}')

    def save_dropdown_state(self):
        try:
            with self.call_stack.track_function():
                self.dropdown_state = {}
                for row in range(self.rowCount()):
                    for column_index in self.dropdown_options.keys():
                        if dropdown := self.cellWidget(row, column_index):
                            self.dropdown_state[(row, column_index)] = dropdown.currentText()
        except Exception as e:
            logger.error(f'Failed to save dropdown state\n{get_trace(e)}')

    def restore_dropdown_state(self):
        try:
            with self.call_stack.track_function():
                for (row, column_index), value in self.dropdown_state.items():
                    if dropdown := self.cellWidget(row, column_index):
                        dropdown.setCurrentText(value)
        except Exception as e:
            logger.error(f'Failed to restore dropdown state\n{get_trace(e)}')

    def ensure_one_empty_row(self):
        try:
            with self.call_stack.track_function():
                self.save_dropdown_state()  # Save the current state of dropdowns
                if self.should_ensure_empty_row:
                    last_row_index = self.rowCount() - 1
                    if last_row_index >= 0:
                        # Check if the last row is empty
                        column_range = range(self.columnCount())
                        if self.table_name == "RotationBuilder": # Ignore the In-Game Time
                            column_range = tuple(
                                col for col in column_range if col != 2
                            )
                        last_row_empty = all(
                            self.item(last_row_index, col) is None or self.item(last_row_index, col).text() == ''
                            for col in column_range
                        )
                        if not last_row_empty:
                            self.insertRow(self.rowCount())
                            self.apply_dropdowns()
                            # Initialize dropdowns in the newly added row
                            self.initialize_row_dropdowns(self.rowCount() - 1)
                            if self.table_name == "RotationBuilder":
                                # Set In-Game Time to the value in the previous row
                                self.setItem(last_row_index + 1, 2, QTableWidgetItem(self.item(last_row_index, 2).text()))
                    else:
                        # If there are no rows, insert the first row
                        self.insertRow(0)
                        self.apply_dropdowns()
                        # Initialize dropdowns in the newly added row
                        self.initialize_row_dropdowns(0)
                        if self.table_name == "RotationBuilder":
                            # Set In-Game Time to 0
                            self.setItem(0, 2, QTableWidgetItem("0.00"))
                self.restore_dropdown_state()  # Restore the state of dropdowns
        except Exception as e:
            logger.error(f'Failed to ensure one empty row\n{get_trace(e)}')

    def initialize_row_dropdowns(self, row):
        try:
            with self.call_stack.track_function():
                for column_index, options in self.dropdown_options.items():
                    if dropdown := self.cellWidget(row, column_index):
                        dropdown.clear()
                        dropdown.addItems(options)
                        dropdown.setCurrentText("")
                        self.update_dropdown_value_from_database(row, column_index, dropdown)
        except Exception as e:
            logger.error(f'Failed to initialize row dropdowns\n{get_trace(e)}')

    def update_dropdown(self, row, column, character, options):
        try:
            with self.call_stack.track_function():
                if self.cellWidget(row, column) is not None:
                    dropdown = self.cellWidget(row, column)
                    current_value = dropdown.currentText()
                    dropdown.clear()
                    dropdown.addItems(options)
                    dropdown.setCurrentText(current_value or "")
                    self.dropdown_options[column][character] = options
        except Exception as e:
            logger.error(f'Failed to update dropdown\n{get_trace(e)}')

    def update_dependent_dropdowns(self, row, column):
        try:
            with self.call_stack.track_function():
                match(self.table_name):
                    case "CharacterLineup":
                        if column == 0:  # Character column
                            item = self.item(row, column)
                            if item is None:
                                character = self.cellWidget(row, column).currentText()
                            else:
                                character = item.text()
                            if character is None:
                                logger.warning(f"Item at row {row}, column {column} in table {self.table_name} is None")
                            else:
                                if character != "":
                                    weapon_options = ["Nullify Damage"] + fetch_data_from_database(
                                        CONSTANTS_DB_PATH, "Weapons", columns="Weapon", 
                                        where_clause=f"WeaponType = (SELECT Weapon FROM CharacterConstants WHERE Character = '{character}')"
                                    )
                                else:
                                    weapon_options = [""]
                                self.update_dropdown(row, 2, character, weapon_options)  # Update weapon dropdown (column 2)
                    case "RotationBuilder":
                        if column == 0:  # Character column
                            item = self.item(row, column)
                            if item is None:
                                character = self.cellWidget(row, column).currentText()
                            else:
                                character = item.text()
                            if character is None:
                                logger.warning(f"Item at row {row}, column {column} in table {self.table_name} is None")
                            else:
                                if character != "":
                                    skill_options = (
                                        [""] +
                                        fetch_data_from_database(f'{CHARACTERS_DB_PATH}/{character}.db', "Intro", columns="Skill") +
                                        fetch_data_from_database(f'{CHARACTERS_DB_PATH}/{character}.db', "Outro", columns="Skill") +
                                        list(fetch_data_comparing_two_databases(
                                            CONSTANTS_DB_PATH, "Echoes", 
                                            CALCULATOR_DB_PATH, "CharacterLineup", 
                                            columns1="Echo", columns2="", 
                                            where_clause=f"t2.Character = '{character}' AND t1.Echo LIKE t2.Echo || '%'")) +
                                        fetch_data_from_database(f'{CHARACTERS_DB_PATH}/{character}.db', "Skills", columns="Skill")
                                    )
                                else:
                                    skill_options = [""]
                                self.update_dropdown(row, 1, character, skill_options)  # Update skill dropdown (column 1)
        except Exception as e:
            logger.error(f'Failed to update dependent dropdowns\n{get_trace(e)}')

    def update_subsequent_in_game_times(self, row):
        try:
            with self.call_stack.track_function():
                i = 1
                while self.item(row + i, 2):
                    in_game_time = float(self.item(row + i - 1, 2).text()) if row + i > 0 else 0.0
                    time_to_add = None
                    character_name = self.cellWidget(row + i - 1, 0).currentText()
                    skill_name = self.cellWidget(row + i - 1, 1).currentText()
                    if "" not in (character_name, skill_name):
                        time_delay = fetch_data_from_database(CALCULATOR_DB_PATH, "RotationBuilder", columns="TimeDelay", where_clause=f"ID = '{row + i + 1}'")
                        time_delay = 0 if time_delay == [] or time_delay[0] is None else time_delay[0]
                        if skill_name.startswith("Intro:"):
                            try:
                                time_to_add = fetch_data_from_database(f'{CHARACTERS_DB_PATH}/{character_name}.db', "Intro", columns="Time", where_clause=f'Skill = "{skill_name}"')[0]
                            except IndexError:
                                logger.info(f'Skill name {skill_name} has not been found in Intro table, searching Skills table')
                        elif skill_name.startswith("Outro:"):
                            try:
                                time_to_add = fetch_data_from_database(f'{CHARACTERS_DB_PATH}/{character_name}.db', "Outro", columns="Time", where_clause=f'Skill = "{skill_name}"')[0]
                            except IndexError:
                                logger.info(f'Skill name {skill_name} has not been found in Outro table, searching Skills table')
                        if time_to_add is None:
                            try:
                                time_to_add = fetch_data_from_database(f'{CHARACTERS_DB_PATH}/{character_name}.db', "Skills", columns="Time - IFNULL(FreezeTime, 0)", where_clause=f'Skill = "{skill_name}"')[0] 
                            except IndexError:
                                logger.info(f'Skill name {skill_name} has not been found in Skills table, searching Echo table')
                        if time_to_add is None:
                            try:
                                time_to_add = fetch_data_from_database(CONSTANTS_DB_PATH, "Echoes", columns="Time", where_clause=f'Echo = "{skill_name}"')[0]
                            except IndexError:
                                logger.warning(f'Skill name {skill_name} has not been found in Echo table')
                        if time_to_add is None:
                            logger.error(f'Skill {skill_name} could not be found for character {character_name}')
                        else:
                            self.item(row + i, 2).setText(str(in_game_time + time_to_add + time_delay))
                    i += 1
                self.save_table_data()
        except Exception as e:
            logger.error(f'Failed to update subsequent in-game times\n{get_trace(e)}')

    def on_dropdown_changed(self, row, column):
        try:
            if self.call_stack.get_stack(): # Make sure this isn't running because of some other function
                return
            with self.call_stack.track_function():
                logger.info(f"Dropdown changed at row {row}, column {column} in table {self.table_name}")
                if self.cellWidget(row, column):
                    dropdown = self.cellWidget(row, column)
                    selected_value = dropdown.currentText()
                    self.setItem(row, column, QTableWidgetItem(selected_value))
                    self.update_dependent_dropdowns(row, column)
                    self.ensure_one_empty_row()
                    self.save_table_data()
                    if self.table_name == "RotationBuilder": # Update the In-Game Time of the next rows
                        self.update_subsequent_in_game_times(row)
        except Exception as e:
            logger.error(f'Failed to process on_dropdown_changed\n{get_trace(e)}')

    def on_cell_changed(self, row, column):
        try:
            if self.call_stack.get_stack(): # Make sure this isn't running because of some other function
                return
            with self.call_stack.track_function():
                logger.info(f"Cell changed at row {row}, column {column} in table {self.table_name}")
                if column in self.dropdown_options:
                    self.update_dependent_dropdowns(row, column)
                self.ensure_one_empty_row()
                self.save_table_data()
        except Exception as e:
            logger.error(f'Failed to process on_cell_changed\n{get_trace(e)}')

    def setup_table(self, db_name, table_name, column_labels, dropdown_options=None):
        try:
            with self.call_stack.track_function():
                self.db_name = db_name
                self.table_name = table_name
                self.column_labels = column_labels
                
                self.cell_attributes = {column: {} for column in self.column_labels}

                if dropdown_options:
                    self.dropdown_options = dropdown_options
                
                config = load_config(CONFIG_PATH)
                if db_name not in (CONSTANTS_DB_PATH, CALCULATOR_DB_PATH):
                    db_name = "characters"
                for table in config[db_name]["tables"]:
                    if table_name == table["table_name"]:
                        self.db_columns = list(table["db_columns"].keys())
                        break
        except Exception as e:
            logger.error(f'Failed to setup table\n{get_trace(e)}')

    def get_column_index_by_name(self, column_name):
        """Fetches the column index by its name."""
        with self.call_stack.track_function():
            return next(
                (
                    col
                    for col in range(len(self.column_labels))
                    if self.column_labels[col] == column_name
                ),
                None,
            )

    def set_cell_attributes(self, column_name, row, note=None, font_color=None, font_weight=None):
        """
        Set attributes for a specific cell.
        """
        with self.call_stack.track_function():
            if column_name not in self.cell_attributes:
                self.cell_attributes[column_name] = {}

            self.cell_attributes[column_name][row] = {
                'note': note,
                'font_color': font_color,
                'font_weight': font_weight
            }

            # Determine the column number by its name
            col = self.get_column_index_by_name(column_name)
            if col is None:
                logger.error(f'Column {column_name} could not be found in table {self.table_name}')
                return

            # If the cell has a QTableWidgetItem (standard cell)
            if item := self.item(row, col):
                # Apply font color
                if font_color:
                    item.setForeground(QColor(font_color))

                # Apply font weight
                font = item.font()
                if font_weight:
                    font.setWeight(font_weight)
                    item.setFont(font)

                # Apply note
                if note:
                    item.setToolTip(note)
            
            # If the cell contains a CustomComboBox (dropdown)
            if widget := self.cellWidget(row, self.get_column_index_by_name(column_name)):
                if isinstance(widget, CustomComboBox):
                    # Apply font color
                    if font_color:
                        widget.setStyleSheet(f"color: {font_color};")

                    # Apply font weight
                    font = widget.font()
                    if font_weight:
                        font.setWeight(font_weight)
                        widget.setFont(font)

                    # Apply note as a tooltip
                    if note:
                        widget.setToolTip(note)

    def apply_cell_attributes(self):
        """
        Apply stored attributes (notes, font colors, weights) to all cells.
        """
        with self.call_stack.track_function():
            for column_name, rows in self.cell_attributes.items():
                for row, attributes in rows.items():
                    note = attributes.get('note')
                    font_color = attributes.get('font_color')
                    font_weight = attributes.get('font_weight')
                    self.set_cell_attributes(column_name, row, note, font_color, font_weight)

    def clear_cell_attributes(self):
        """
        Clear all attributes (notes, font colors, weights) for all cells in the table.
        """
        with self.call_stack.track_function():
            # Reset the cell_attributes dictionary
            self.cell_attributes = {column: {} for column in range(self.columnCount())}

            # Clear the attributes from all cells in the table
            for row in range(self.rowCount()):
                for col in range(self.columnCount()):
                    if item := self.item(row, col):
                        # Clear the tooltip (note)
                        item.setToolTip("")

                        # Reset the font color to default
                        item.setForeground(QBrush())

                        # Reset the font weight to default
                        font = item.font()
                        font.setWeight(QFont.Normal)
                        item.setFont(font)

            logging.info("All cell attributes have been cleared.")

    def load_table_data(self):
        try:
            with self.call_stack.track_function():
                table_data = fetch_data_from_database(self.db_name, self.table_name)

                self.setRowCount(0)
                self.setColumnCount(len(self.column_labels))
                self.setHorizontalHeaderLabels(self.column_labels)

                for row_number, row_data in enumerate(table_data):
                    self.insertRow(row_number)
                    for column_number, data in enumerate(row_data):
                        if column_number in self.dropdown_options:
                            dropdown = CustomComboBox()
                            options = [str(option) for option in self.dropdown_options[column_number]]
                            dropdown.addItems(options)
                            if data is not None:
                                dropdown.setCurrentText(str(data))
                            else:
                                dropdown.setCurrentText("")
                            self.setCellWidget(row_number, column_number, dropdown)

                            dropdown.currentIndexChanged.connect(lambda _, r=row_number, c=column_number: self.on_dropdown_changed(r, c))
                        else:
                            display_data = "" if data is None else str(data)
                            self.setItem(row_number, column_number, QTableWidgetItem(display_data))

                if self.dropdown_options:
                    self.apply_dropdowns()

                self.ensure_one_empty_row()

                self.apply_checkbox_columns()

                # Initialize dependent dropdowns if any
                for row in range(self.rowCount()):
                    for column in self.dropdown_options:
                        self.update_dependent_dropdowns(row, column)

                # Apply cell attributes like notes, colors, and font weights
                self.apply_cell_attributes()

                # Adjust column widths after data and dropdowns are set
                for i in range(self.columnCount()):
                    self.resizeColumnToContents(i)
                    if self.columnWidth(i) > 200:
                        self.setColumnWidth(i, 200)

                header = self.horizontalHeader()
                header.setSectionResizeMode(QHeaderView.Interactive)

        except Exception as e:
            logger.error(f'Failed to load table data\n{get_trace(e)}')

    def save_table_data(self):
        try:
            with self.call_stack.track_function():
                # Initialize an empty list to store modified row data
                modified_rows = []

                # Loop through the rows in the table
                for row in range(self.rowCount()):
                    row_data = {}
                    row_modified = False
                    
                    # Loop through the columns in each row
                    for col in range(self.columnCount()):
                        item = self.item(row, col)
                        cell_data = None

                        if item:
                            cell_data = item.text()
                        elif self.cellWidget(row, col):
                            # Handle dropdown cell
                            dropdown = self.cellWidget(row, col)
                            cell_data = dropdown.currentText()

                        # Check if this cell has data
                        if cell_data:
                            row_data[self.db_columns[col]] = cell_data
                            row_modified = True

                    if self.table_name == "RotationBuilder": # Ignore incomplete rows in the Rotation Builder table
                        character_name = self.cellWidget(row, 0).currentText()
                        skill_name = self.cellWidget(row, 1).currentText()
                        if "" in (character_name, skill_name):
                            row_modified = False

                    # If the row has been modified, add it to the list
                    if row_modified:
                        # Calculate the row ID based on the row number (index starts at 0, ID starts at 1)
                        row_id = row + 1
                        row_data["ID"] = row_id
                        modified_rows.append(row_data)

                # Only update rows in the database that have been modified
                if modified_rows:
                    overwrite_table_data_by_row_ids(self.db_name, self.table_name, modified_rows)
                    logging.info(f"Modified data for '{self.table_name}' has been saved successfully.")
        except Exception as e:
            logger.error(f'Failed to save table data\n{get_trace(e)}')

    def apply_checkbox_columns(self):
        try:
            with self.call_stack.track_function():
                for column_index in self.checkbox_columns:
                    for row in range(self.rowCount()):
                        item = self.item(row, column_index)
                        boolean_value = item.text() == "TRUE" if item is not None else False
                        checkbox_item = CheckBoxItem()
                        checkbox_item.setFlags(checkbox_item.flags() | Qt.ItemIsUserCheckable)
                        checkbox_item.setCheckState(Qt.Checked if boolean_value else Qt.Unchecked)

                        self.setItem(row, column_index, checkbox_item)
        except Exception as e:
            logger.error(f'Failed to replace boolean column with checkboxes\n{get_trace(e)}')

    def get_column_check_states(self, column_index):
        try:
            with self.call_stack.track_function():
                check_states = []
                for row in range(self.rowCount()):
                    item = self.item(row, column_index)
                    if item is not None:
                        check_states.append(item.checkState() == Qt.Checked)
                    else:
                        check_states.append(False)
                return check_states
        except Exception as e:
            logger.error(f'Failed to get column check states\n{get_trace(e)}')

    def show_context_menu(self, pos):
        try:
            with self.call_stack.track_function():
                menu = QMenu()
                
                menu.addAction(self.copy_action)
                menu.addAction(self.paste_action)
                menu.addAction(self.undo_action)
                menu.addAction(self.redo_action)
                
                menu.exec_(self.mapToGlobal(pos))
        except Exception as e:
            logger.error(f'Failed to show context menu\n{get_trace(e)}')

    def copy_selection(self):
        try:
            with self.call_stack.track_function():
                selected_items = self.selectedItems()
                if not selected_items:
                    return
                
                clipboard = QApplication.clipboard()
                selected_range = self.selectedRanges()[0]
                top_row = selected_range.topRow()
                bottom_row = selected_range.bottomRow()
                left_col = selected_range.leftColumn()
                right_col = selected_range.rightColumn()

                data = []
                for row in range(top_row, bottom_row + 1):
                    row_data = []
                    for col in range(left_col, right_col + 1):
                        item = self.item(row, col)
                        if self.cellWidget(row, col):
                            item = self.cellWidget(row, col).currentText()
                        row_data.append(item.text() if item else "")
                    data.append("\t".join(row_data))
                clipboard.setText("\n".join(data))
        except Exception as e:
            logger.error(f'Failed to copy selection\n{get_trace(e)}')

    def paste_selection(self):
        try:
            with self.call_stack.track_function():
                clipboard = QApplication.clipboard()
                data = clipboard.text()
                rows = data.split("\n")

                selected_range = self.selectedRanges()[0] if self.selectedRanges() else None
                if not selected_range:
                    return

                start_row = selected_range.topRow()
                start_col = selected_range.leftColumn()

                if start_col + len(rows[0].split("\t")) > self.columnCount():
                    logging.warning("Paste exceeds column count, trimming data.")
                    rows = [row.split("\t")[:self.columnCount() - start_col] for row in rows]

                # Capture the current state for undo
                original_state = self.get_table_state(start_row, start_col, len(rows), len(rows[0]))

                for row_index, row_data in enumerate(rows):
                    if row_index + start_row >= self.rowCount():
                        self.insertRow(self.rowCount())
                    columns = row_data.split("\t")
                    for col_index, cell_data in enumerate(columns):
                        if col_index + start_col >= self.columnCount():
                            break  # Prevent pasting past the last column
                        if self.cellWidget(row_index + start_row, col_index + start_col):
                            # Handle dropdown cells
                            dropdown = self.cellWidget(row_index + start_row, col_index + start_col)
                            dropdown.setCurrentText(cell_data)
                        else:
                            self.setItem(row_index + start_row, col_index + start_col, QTableWidgetItem(cell_data))
                
                self.undo_stack.push(PasteCommand(self, start_row, start_col, rows, original_state))
        except Exception as e:
            logger.error(f'Failed to paste selection\n{get_trace(e)}')

    def get_table_state(self, start_row, start_col, num_rows, num_cols):
        try:
            with self.call_stack.track_function():
                state = {}
                for row in range(start_row, start_row + num_rows):
                    if row >= self.rowCount():
                        break
                    for col in range(start_col, start_col + num_cols):
                        if col >= self.columnCount():
                            break
                        if item := self.item(row, col):
                            state[(row, col)] = item.text()
                        elif self.cellWidget(row, col):
                            dropdown = self.cellWidget(row, col)
                            state[(row, col)] = dropdown.currentText()
                return state
        except Exception as e:
            logger.error(f'Failed to get the table state\n{get_trace(e)}')

    def keyPressEvent(self, event):
        try:
            with self.call_stack.track_function():
                key = event.key()
                modifiers = event.modifiers()

                if key == Qt.Key_C and modifiers & Qt.ControlModifier:
                    self.copy_action.trigger()
                elif key == Qt.Key_V and modifiers & Qt.ControlModifier:
                    self.paste_action.trigger()
                elif key == Qt.Key_Z and modifiers & Qt.ControlModifier:
                    self.undo_action.trigger()
                elif key == Qt.Key_Y and modifiers & Qt.ControlModifier:
                    self.redo_action.trigger()
                else:
                    super(CustomTableWidget, self).keyPressEvent(event)
        except Exception as e:
            logger.error(f'Exception in keyPressEvent\n{get_trace(e)}')

def get_trace(ex: BaseException):
    return ''.join(traceback.TracebackException.from_exception(ex).format())