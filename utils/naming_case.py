"""
Naming Case
===========

by @HikariTenshi

This module provides utility functions for converting strings between camelCase and snake_case.

Functions
---------
- camel_to_snake(camel_str): Converts a camelCase string to snake_case.
- snake_to_camel(snake_str): Converts a snake_case string to camelCase.
"""

def camel_to_snake(camel_str):
    """
    Convert a camelCase string to snake_case.

    This function takes a camelCase string and converts it to snake_case by
    inserting underscores before uppercase letters and converting them to lowercase.

    Parameters
    ----------
    camel_str : str
        The camelCase string to convert.

    Returns
    -------
    str
        The converted snake_case string.

    Examples
    --------
    >>> camel_to_snake("thisIsCamelCase")
    'this_is_camel_case'

    >>> camel_to_snake("CamelCase")
    'camel_case'

    >>> camel_to_snake("already_snake_case")
    'already_snake_case'
    """
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

def snake_to_camel(snake_str):
    """
    Convert a snake_case string to camelCase.

    This function takes a snake_case string and converts it to camelCase by
    capitalizing the first letter of each word (except for the first word) and
    removing underscores.

    Parameters
    ----------
    snake_str : str
        The snake_case string to convert.

    Returns
    -------
    str
        The converted camelCase string.

    Examples
    --------
    >>> snake_to_camel("this_is_snake_case")
    'thisIsSnakeCase'

    >>> snake_to_camel("snake_case")
    'snakeCase'

    >>> snake_to_camel("alreadyCamelCase")
    'alreadycamelcase'
    """
    if not snake_str:
        return ""

    # Split the string by underscores
    words = snake_str.split('_')

    # Capitalize the first letter of each word except the first one
    camel_case = [words[0].lower()]  # The first word should be lowercase
    camel_case.extend(word.capitalize() for word in words[1:])

    # Join all parts together
    return "".join(camel_case)