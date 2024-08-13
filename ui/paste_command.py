"""
PasteCommand
============

by @HikariTenshi

This module defines a custom `QUndoCommand` class that handles the paste operation within a `QTableWidget`.
It allows for undoing and redoing the paste operation, preserving the original state of the table.

Module Dependencies
-------------------
- **PyQt5.QtWidgets**: Provides the `QUndoCommand` and `QTableWidgetItem` classes.

Class Definitions
-----------------
**PasteCommand**: A custom implementation of `QUndoCommand` for handling paste operations in a `QTableWidget`.

    - **__init__(self, table_widget, start_row, start_col, rows, original_state)**:
      Initializes the command with the target table, the starting cell, the data to paste, and the original state of the table.

    - **undo(self)**:
      Reverts the table to its original state before the paste operation.

    - **redo(self)**:
      Executes the paste operation, inserting data into the table starting from the specified cell.

Usage Example:

    from PyQt5.QtWidgets import QTableWidget, QApplication
    from your_module import PasteCommand # Replace 'your_module' with the actual module name

    app = QApplication([])
    table_widget = QTableWidget(5, 5)
    original_state = {} # Capture the original state of the table
    rows_to_paste = ["data1", "data2", "data3", "data4"]
    paste_command = PasteCommand(table_widget, 0, 0, rows_to_paste, original_state)
    paste_command.redo() # Perform the paste operation
"""

from PyQt5.QtWidgets import QUndoCommand, QTableWidgetItem

class PasteCommand(QUndoCommand):
    """
    A custom command for pasting data into a QTableWidget.
    
    This class extends `QUndoCommand` to allow pasting data into a specified range
    of cells in a `QTableWidget`. It supports undo and redo functionality, maintaining
    the original state of the table for rollback purposes.
    
    Attributes
    ----------
    table_widget : QTableWidget
        The table widget where data is being pasted.
    start_row : int
        The row index where the paste operation starts.
    start_col : int
        The column index where the paste operation starts.
    rows : list of str
        The data rows to paste, each element containing tab-separated values for each column.
    original_state : dict
        A dictionary storing the original state of the table before the paste operation.
    """
    
    def __init__(self, table_widget, start_row, start_col, rows, original_state):
        """
        Initializes the PasteCommand with the necessary data.

        :param table_widget: The target table widget where the data will be pasted.
        :type table_widget: QTableWidget
        :param start_row: The starting row index for the paste operation.
        :type start_row: int
        :param start_col: The starting column index for the paste operation.
        :type start_col: int
        :param rows: The data rows to paste, each element containing tab-separated column values.
        :type rows: list of str
        :param original_state: The original state of the table, captured as a dictionary with (row, col) keys.
        :type original_state: dict
        """
        super().__init__()
        self.table_widget = table_widget
        self.start_row = start_row
        self.start_col = start_col
        self.rows = rows
        self.original_state = original_state

    def undo(self):
        """
        Reverts the table to its original state before the paste operation.

        This method iterates through the original state dictionary and restores
        the content of each cell to what it was before the paste operation.
        """
        for (row, col), value in self.original_state.items():
            if self.table_widget.cellWidget(row, col):
                dropdown = self.table_widget.cellWidget(row, col)
                dropdown.setCurrentText(value)
            else:
                self.table_widget.setItem(row, col, QTableWidgetItem(value))

    def redo(self):
        """
        Executes the paste operation.

        This method inserts the provided data into the table, starting from the specified
        row and column. If necessary, it adds new rows to accommodate the pasted data,
        and handles both regular cells and cells containing dropdown widgets.
        """
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