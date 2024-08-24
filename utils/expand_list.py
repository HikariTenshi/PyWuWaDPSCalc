"""
Expand List
===========

by @HikariTenshi

This module provides utility functions to manipulate lists by setting values
at specific indices or adding values to existing elements, even if the target
index is initially out of bounds.

Functions
---------
- set_value_at_index(lst, index, value): Sets a value at a specific index, extending
  the list with `None` values if the index is out of bounds.
  
- add_to_list(lst, index, value): Adds a value to an existing element at a specific
  index, extending the list with `None` values if the index is out of bounds.
"""

def set_value_at_index(lst, index, value):
    """
    Sets the value at a specific index in a list. If the index is out of bounds,
    the list is extended with None values up to that index.

    Parameters
    ----------
    lst : list
        The list in which to set the value.
    index : int
        The index at which to set the value.
    value : any
        The value to set at the specified index.

    Examples
    --------
    >>> my_list = [1, 2, 3]
    >>> set_value_at_index(my_list, 5, 10)
    >>> print(my_list)
    [1, 2, 3, None, None, 10]
    """
    if index >= len(lst):
        # Extend the list with None values up to the desired index
        lst.extend([None] * (index + 1 - len(lst)))
    
    # Set the value at the specified index
    lst[index] = value

def add_to_list(lst, index, value):
    """
    Adds a value to the element at the specified index in the list. 
    If the index is out of bounds, the list is extended with None values up to that index.

    Parameters
    ----------
    lst : list
        The list in which to add the value.
    index : int
        The index at which to add the value.
    value : any
        The value to add to the specified index.

    Examples
    --------
    >>> my_list = [10, 20, 30]
    >>> add_to_list(my_list, 5, 5)
    >>> print(my_list)
    [10, 20, 30, None, None, 5]

    >>> add_to_list(my_list, 1, 15)
    >>> print(my_list)
    [10, 35, 30, None, None, 5]
    """
    if index >= len(lst):
        lst.extend([None] * (index + 1 - len(lst)))
    
    if lst[index] is None:
        lst[index] = value
    else:
        lst[index] += value