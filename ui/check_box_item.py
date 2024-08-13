"""
CheckBoxItem Module
===================

by @HikariTenshi

This module defines a custom `QTableWidgetItem` class that adds a checkbox to each item in a `QTableWidget`.
The custom item allows for managing the checked state within the table.

Module Dependencies
-------------------
- **PyQt5.QtWidgets**: Provides the `QTableWidgetItem` class.
- **PyQt5.QtCore**: Provides the `Qt` enumeration for item flag and check state management.

Class Definitions
-----------------
**CheckBoxItem**: A custom implementation of `QTableWidgetItem` with a checkbox.

    - **__init__(self, text="")**:
      Initializes the table widget item with optional text and adds a checkbox in an unchecked state.
    
    - **is_checkable(self)**:
      Returns whether the item is checkable. In this implementation, always returns `True`.

Usage Example:

    from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QApplication
    from your_module import CheckBoxItem  # Replace 'your_module' with the actual module name

    app = QApplication([])
    table_widget = QTableWidget(3, 3)
    checkbox_item = CheckBoxItem("Item with Checkbox")
    table_widget.setItem(0, 0, checkbox_item)
"""

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt

class CheckBoxItem(QTableWidgetItem):
    """
    A custom table widget item that includes a checkbox.
    
    This class extends `QTableWidgetItem` to include a checkbox that can be
    checked or unchecked by the user. The item is initialized with an optional
    text label and the checkbox in an unchecked state.
    """

    def __init__(self, text=""):
        """
        Initializes the custom table widget item with a checkbox.

        :param text: The text label for the item (optional).
        :type text: str
        """
        super(CheckBoxItem, self).__init__(text)
        self.setFlags(self.flags() | Qt.ItemIsUserCheckable)
        self.setCheckState(Qt.Unchecked)

    def is_checkable(self):
        """
        Indicates that the item is checkable.

        :return: Always returns `True`.
        :rtype: bool
        """
        return True