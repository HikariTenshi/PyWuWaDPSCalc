import logging
import traceback
from PyQt5.QtWidgets import QApplication, QTableWidget, QMenu, QAction, QTableWidgetItem, QUndoStack, QUndoCommand, QComboBox, QHeaderView
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt
from utils.database_io import fetch_data_from_database, overwrite_table_data
from utils.config_io import load_config

CONSTANTS_DB_PATH = "databases/constants.db"
CALCULATOR_DB_PATH = "databases/calculator.db"
CONFIG_PATH = "databases/table_config.json"
CHARACTER_DATABASE_FOLDER_PATH = "databases/characters"

# Configure logging
logging.basicConfig(level=logging.INFO)
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

            # Connect cell changed signal
            self.cellChanged.connect(self.on_cell_changed)

            self.setup_in_progress = False
        except Exception as e:
            logger.error("Failed to init the CustomTableWidget")
            logger.error(get_trace(e))
            raise

    def update_dropdown_value_from_database(self, row, column, dropdown):
        try:
            where_clause = f'ID = {row + 1}'
            current_value_list = fetch_data_from_database(self.db_name, self.table_name, columns=self.db_columns[column], where_clause=where_clause)
            current_value = str(current_value_list[0]) if current_value_list else ""
            dropdown.setCurrentText(current_value)
        except Exception as e:
            logger.error("Failed to update dropdown value from database")
            logger.error(get_trace(e))
            raise

    def apply_dropdowns(self):
        try:
            self.blockSignals(True)
            for column_index, options in self.dropdown_options.items():
                options = [str(option) for option in options]
                for row in range(self.rowCount()):
                    dropdown = self.cellWidget(row, column_index)
                    if dropdown is None:
                        dropdown = QComboBox()
                        dropdown.addItems(options)
                        dropdown.setEditable(False)
                        dropdown.currentIndexChanged.connect(lambda _, r=row, c=column_index: self.on_dropdown_changed(r, c))
                        self.setCellWidget(row, column_index, dropdown)
                    else:
                        current_value = dropdown.currentText()
                        dropdown.clear()
                        dropdown.addItems(options)
                        dropdown.setCurrentText(current_value or "")
                    # Initialize dropdown value from database
                    self.update_dropdown_value_from_database(row, column_index, dropdown)
        except Exception as e:
            logger.error("Failed to apply dropdowns")
            logger.error(get_trace(e))
            raise
        finally:
            self.blockSignals(False)

    def add_dropdown_to_column(self, column_index, items):
        try:
            self.setup_in_progress = True
            items = [str(item) for item in items]
            for row in range(self.rowCount()):
                dropdown = self.cellWidget(row, column_index)
                if dropdown is None:
                    dropdown = QComboBox()
                    dropdown.addItems(items)
                    dropdown.setEditable(False)
                    dropdown.currentIndexChanged.connect(lambda _, r=row, c=column_index: self.on_dropdown_changed(r, c))
                    self.setCellWidget(row, column_index, dropdown)
                else:
                    current_value = dropdown.currentText()
                    dropdown.clear()
                    dropdown.addItems(items)
                    dropdown.setCurrentText(current_value or "")
        except Exception as e:
            logger.error("Failed to add dropdown")
            logger.error(get_trace(e))
            raise
        finally:
            self.setup_in_progress = False

    def save_dropdown_state(self):
        try:
            self.dropdown_state = {}
            for row in range(self.rowCount()):
                for column_index in self.dropdown_options.keys():
                    if dropdown := self.cellWidget(row, column_index):
                        self.dropdown_state[(row, column_index)] = dropdown.currentText()
        except Exception as e:
            logger.error("Failed to save dropdown state")
            logger.error(get_trace(e))
            raise

    def restore_dropdown_state(self):
        try:
            for (row, column_index), value in self.dropdown_state.items():
                if dropdown := self.cellWidget(row, column_index):
                    dropdown.setCurrentText(value)
        except Exception as e:
            logger.error("Failed to restore dropdown state")
            logger.error(get_trace(e))
            raise

    def ensure_one_empty_row(self):
        try:
            self.blockSignals(True)  # Block signals before ensuring one empty row
            self.save_dropdown_state()  # Save the current state of dropdowns
            if self.should_ensure_empty_row:
                last_row_index = self.rowCount() - 1
                if last_row_index >= 0:
                    # Check if the last row is empty
                    last_row_empty = all(
                        self.item(last_row_index, col) is None or self.item(last_row_index, col).text() == ''
                        for col in range(self.columnCount())
                    )
                    if not last_row_empty:
                        self.insertRow(self.rowCount())
                        self.apply_dropdowns()
                        # Initialize dropdowns in the newly added row
                        self.initialize_row_dropdowns(self.rowCount() - 1)
                else:
                    # If there are no rows, insert the first row
                    self.insertRow(0)
                    self.apply_dropdowns()
                    # Initialize dropdowns in the newly added row
                    self.initialize_row_dropdowns(0)
            self.restore_dropdown_state()  # Restore the state of dropdowns
        except Exception as e:
            logger.error("Failed to ensure one empty row")
            logger.error(get_trace(e))
            raise
        finally:
            self.blockSignals(False)  # Unblock signals after ensuring one empty row

    def initialize_row_dropdowns(self, row):
        try:
            for column_index, options in self.dropdown_options.items():
                if dropdown := self.cellWidget(row, column_index):
                    dropdown.clear()
                    dropdown.addItems(options)
                    dropdown.setCurrentText("")
        except Exception as e:
            logger.error("Failed to initialize row dropdowns")
            logger.error(get_trace(e))
            raise

    def update_dropdown(self, row, column, options):
        try:
            self.blockSignals(True) # Block signals before updating the dropdown
            if self.cellWidget(row, column) is not None:
                dropdown = self.cellWidget(row, column)
                current_value = dropdown.currentText()
                print(f'{current_value = }')
                dropdown.clear()
                dropdown.addItems(options)
                dropdown.setCurrentText(current_value or "")
        except Exception as e:
            logger.error("Failed to update dropdown")
            logger.error(get_trace(e))
            raise
        finally:
            self.blockSignals(False) # Unblock signals after updating the dropdown

    def update_dependent_dropdowns(self, row, column):
        try:
            match(self.table_name):
                case "CharacterLineup":
                    if column == 0:  # Character column
                        item = self.item(row, column)
                        if item is None:
                            logger.error(f"Item at row {row}, column {column} in table {self.table_name} is None")
                        else:
                            character = item.text()
                            if character != "":
                                weapon_options = [""] + fetch_data_from_database(
                                    CONSTANTS_DB_PATH, "Weapons", columns="Weapon", 
                                    where_clause=f"WeaponType = (SELECT Weapon FROM CharacterConstants WHERE Character = '{character}')"
                                )
                            else:
                                weapon_options = [""]
                            self.update_dropdown(row, 2, weapon_options)  # Update weapon dropdown (column 2)
                case "RotationBuilder":
                    if column == 0:  # Character column
                        item = self.item(row, column)
                        if item is None:
                            logger.error(f"Item at row {row}, column {column} in table {self.table_name} is None")
                        else:
                            character = item.text()
                            if character != "":
                                skill_options = (
                                    [""] +
                                    fetch_data_from_database(f'{CHARACTER_DATABASE_FOLDER_PATH}/{character}.db', "Intro", columns="Skill") +
                                    fetch_data_from_database(f'{CHARACTER_DATABASE_FOLDER_PATH}/{character}.db', "Outro", columns="Skill") +
                                    fetch_data_from_database(f'{CHARACTER_DATABASE_FOLDER_PATH}/{character}.db', "Skills", columns="Skill")
                                )
                            else:
                                skill_options = [""]
                            self.update_dropdown(row, 1, skill_options)  # Update skill dropdown (column 1)
        except Exception as e:
            logger.error("Failed to update dependent dropdowns")
            logger.error(get_trace(e))
            raise

    def on_dropdown_changed(self, row, column):
        try:
            if self.setup_in_progress:
                return
            # logger.info(f"Dropdown changed at row {row}, column {column}")
            if self.cellWidget(row, column):
                dropdown = self.cellWidget(row, column)
                selected_value = dropdown.currentText()
                self.setItem(row, column, QTableWidgetItem(selected_value))
                self.update_dependent_dropdowns(row, column)  # Update dependent dropdowns
                self.ensure_one_empty_row()
                self.save_table_data()
        except Exception as e:
            logger.error("Failed to process on_dropdown_changed")
            logger.error(get_trace(e))
            raise

    def on_cell_changed(self, row, column):
        try:
            # logger.info(f"Cell changed at row {row}, column {column}")
            if column in self.dropdown_options:
                self.update_dependent_dropdowns(row, column)
            self.ensure_one_empty_row()
            self.save_table_data()
        except Exception as e:
            logger.error("Failed to process on_cell_changed")
            logger.error(get_trace(e))
            raise

    def setup_table(self, db_name, table_name, column_labels, dropdown_options=None):
        try:
            self.db_name = db_name
            self.table_name = table_name
            self.column_labels = column_labels

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
            logger.error("Failed to setup table")
            logger.error(get_trace(e))
            raise

    def load_table_data(self):
        self.is_loading = True
        try:
            self.blockSignals(True)
            table_data = fetch_data_from_database(self.db_name, self.table_name)

            self.setRowCount(0)
            self.setColumnCount(len(self.column_labels))
            self.setHorizontalHeaderLabels(self.column_labels)

            for row_number, row_data in enumerate(table_data):
                self.insertRow(row_number)
                for column_number, data in enumerate(row_data):
                    if column_number in self.dropdown_options:
                        # Create and set dropdown
                        dropdown = QComboBox()
                        options = [str(option) for option in self.dropdown_options[column_number]]
                        dropdown.addItems(options)
                        if data is not None:
                            dropdown.setCurrentText(str(data))
                        else:
                            dropdown.setCurrentText("")
                        self.setCellWidget(row_number, column_number, dropdown)

                        # Ensure the table item is set
                        item = self.item(row_number, column_number)
                        if item is None:
                            item = QTableWidgetItem()
                            self.setItem(row_number, column_number, item)
                        item.setText(dropdown.currentText())

                        # Connect dropdown signal to update the table item
                        dropdown.currentTextChanged.connect(lambda text, r=row_number, c=column_number: self.cellWidget(r, c).setCurrentText(text))
                    else:
                        display_data = "" if data is None else str(data)
                        # logger.info(f"Setting item at row {row_number}, column {column_number} with data: {display_data}")
                        self.setItem(row_number, column_number, QTableWidgetItem(display_data))

            for i in range(self.columnCount()):
                self.resizeColumnToContents(i)
                if self.columnWidth(i) > 200:
                    self.setColumnWidth(i, 200)

            header = self.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Interactive)

            self.ensure_one_empty_row()

            if self.dropdown_options:
                self.apply_dropdowns()
                for row in range(self.rowCount()):
                    for column in self.dropdown_options:
                        self.update_dependent_dropdowns(row, column)

        except Exception as e:
            logger.error("Failed to load table data")
            logger.error(get_trace(e))
            raise
        finally:
            self.is_loading = False
            self.blockSignals(False)

    def save_table_data(self):
        if self.is_loading:
            return
        try:
            table_data = []
            for row in range(self.rowCount()):
                row_data = []
                for col in range(self.columnCount()):
                    if item := self.item(row, col):
                        if isinstance(item, CheckBoxItem):
                            # Save checkbox state as "TRUE" or "FALSE"
                            row_data.append("TRUE" if item.checkState() == Qt.Checked else "FALSE")
                        else:
                            # Convert empty strings to None
                            text = item.text()
                            row_data.append(None if text == "" else text)
                    else:
                        # Cell is empty
                        row_data.append(None)

                if len(row_data) == self.columnCount():  # Ensure the row data length matches column count
                    table_data.append(row_data)
                else:
                    logging.warning(f"Row data length mismatch: expected {self.columnCount()}, got {len(row_data)}")

            if table_data:
                overwrite_table_data(self.db_name, self.table_name, table_data)

            logging.info(f"Table data for '{self.table_name}' has been saved successfully.")
        except Exception as e:
            logger.error("Failed to save table data")
            logger.error(get_trace(e))
            raise

    def replace_boolean_column_with_checkboxes(self, column_index):
        try:
            self.blockSignals(True) # Block signals during replacement
            for row in range(self.rowCount()):
                item = self.item(row, column_index)
                if item is not None:
                    boolean_value = item.text().strip().lower() == "true"
                else:
                    boolean_value = False

                checkbox_item = CheckBoxItem()
                checkbox_item.setFlags(checkbox_item.flags() | Qt.ItemIsUserCheckable)
                checkbox_item.setCheckState(Qt.Checked if boolean_value else Qt.Unchecked)

                self.setItem(row, column_index, checkbox_item)
        except Exception as e:
            logger.error("Failed to replace boolean column with checkboxes")
            logger.error(get_trace(e))
            raise
        finally:
            self.blockSignals(False) # Unblock signals after replacement

    def get_column_check_states(self, column_index):
        try:
            check_states = []
            for row in range(self.rowCount()):
                item = self.item(row, column_index)
                if item is not None:
                    check_states.append(item.checkState() == Qt.Checked)
                else:
                    check_states.append(False)
            return check_states
        except Exception as e:
            logger.error("Failed to get column check states")
            logger.error(get_trace(e))
            raise

    def show_context_menu(self, pos):
        try:
            menu = QMenu()
            
            menu.addAction(self.copy_action)
            menu.addAction(self.paste_action)
            menu.addAction(self.undo_action)
            menu.addAction(self.redo_action)
            
            menu.exec_(self.mapToGlobal(pos))
        except Exception as e:
            logger.error("Failed to show context menu")
            logger.error(get_trace(e))
            raise

    def copy_selection(self):
        try:
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
            logger.error("Failed to copy selection")
            logger.error(get_trace(e))
            raise

    def paste_selection(self):
        try:
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
            logger.error("Failed to paste selection")
            logger.error(get_trace(e))
            raise

    def get_table_state(self, start_row, start_col, num_rows, num_cols):
        try:
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
            logger.error("Failed to get the table state")
            logger.error(get_trace(e))
            raise

    def keyPressEvent(self, event):
        try:
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
            logger.error("Exception in keyPressEvent")
            logger.error(get_trace(e))
            raise

class PasteCommand(QUndoCommand):
    def __init__(self, table_widget, start_row, start_col, rows, original_state):
        super().__init__()
        self.table_widget = table_widget
        self.start_row = start_row
        self.start_col = start_col
        self.rows = rows
        self.original_state = original_state

    def undo(self):
        try:
            for (row, col), value in self.original_state.items():
                if self.table_widget.cellWidget(row, col):
                    dropdown = self.table_widget.cellWidget(row, col)
                    dropdown.setCurrentText(value)
                else:
                    self.table_widget.setItem(row, col, QTableWidgetItem(value))
        except Exception as e:
            logger.error("Failed to undo paste")
            logger.error(get_trace(e))
            raise

    def redo(self):
        try:
            for row_index, row_data in enumerate(self.rows):
                if row_index + self.start_row >= self.table_widget.rowCount():
                    self.table_widget.insertRow(self.table_widget.rowCount())
                columns = row_data.split("\t")
                for col_index, cell_data in enumerate(columns):
                    if col_index + self.start_col >= self.table_widget.columnCount():
                        break  # Prevent pasting past the last column
                    if self.table_widget.cellWidget(row_index + self.start_row, col_index + self.start_col):
                        # Handle dropdown cells
                        dropdown = self.table_widget.cellWidget(row_index + self.start_row, col_index + self.start_col)
                        dropdown.setCurrentText(cell_data)
                    else:
                        self.table_widget.setItem(row_index + self.start_row, col_index + self.start_col, QTableWidgetItem(cell_data))
        except Exception as e:
            logger.error("Failed to redo paste")
            logger.error(get_trace(e))
            raise

class CheckBoxItem(QTableWidgetItem):
    def __init__(self, text=""):
        super(CheckBoxItem, self).__init__(text)
        self.setFlags(self.flags() | Qt.ItemIsUserCheckable)  # Make it checkable
        self.setCheckState(Qt.Unchecked)  # Default state is unchecked

    def is_checkable(self):
        return True

def get_trace(ex: BaseException):
    return ''.join(traceback.TracebackException.from_exception(ex).format())