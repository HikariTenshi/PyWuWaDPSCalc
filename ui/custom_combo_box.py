"""
Custom ComboBox
===============

by @HikariTenshi

This module defines a custom `QComboBox` class that extends the functionality of the standard PyQt5 `QComboBox`.
The custom combo box allows for setting text that may not be present in the existing options and ensures
that the new text is added to the list of options.

Module Dependencies
-------------------
- **PyQt5.QtWidgets**: Provides the `QComboBox` class.
- **PyQt5.QtCore**: Provides the `Qt` enumeration for text matching.

Class Definitions
-----------------
**CustomComboBox**: A custom implementation of `QComboBox`.

    - **__init__(self, parent=None)**:
      Initializes the combo box with the given parent. Sets the combo box to be non-editable and prevents insertion of new items.
    
    - **setCurrentText(self, text)**:
      Sets the current text of the combo box. If the text is not already an option, it is added to the combo box's options.
    
    - **currentText(self)**:
      Returns the current text of the combo box.

Usage Example:

    from PyQt5.QtWidgets import QApplication
    from your_module import CustomComboBox  # Replace 'your_module' with the actual module name

    app = QApplication([])
    combo_box = CustomComboBox()
    combo_box.setCurrentText("New Option")
    print(combo_box.currentText())
"""

from PyQt5.QtWidgets import QComboBox
from PyQt5.QtCore import Qt

class CustomComboBox(QComboBox):
    """
    A custom combo box that extends QComboBox to allow for setting
    text that is not present in the existing options.
    
    This class modifies the behavior of the `setCurrentText` method
    to add new text to the combo box's options if it is not already
    present. It also ensures that the current text can be retrieved
    using the `currentText` method.
    """

    def __init__(self, parent=None):
        """
        Initializes the custom combo box.

        :param parent: Optional parent widget.
        :type parent: QWidget or None
        """
        super().__init__(parent)
        self.setEditable(False)
        self.setInsertPolicy(QComboBox.NoInsert)

    def setCurrentText(self, text):
        """
        Sets the current text of the combo box. If the text is not one
        of the existing options, it is added to the combo box.

        :param text: The text to set as the current item.
        :type text: str
        """
        if text not in [self.itemText(i) for i in range(self.count())]:
            # Add the text if it's not one of the options
            self.addItem(text)
            index = self.findText(text, Qt.MatchFixedString)
            self.setCurrentIndex(index)
        super().setCurrentText(text)
    
    def currentText(self):
        """
        Returns the current text of the combo box.

        :return: The current text of the combo box.
        :rtype: str
        """
        return super().currentText()