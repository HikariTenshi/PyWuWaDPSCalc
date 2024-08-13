"""
Function Call Stack Tracker
===========================

This module provides a `FunctionCallStack` class that helps in tracking the call stack of functions. 
It is particularly useful for debugging and logging, allowing you to monitor the entry and exit of 
functions in a structured manner.

Module Dependencies
-------------------
- **logging**: Used for logging the function call stack.
- **contextlib**: Provides the `contextmanager` decorator for creating a context manager.
- **inspect**: Used to retrieve information about the calling function.
- **uuid**: Used to generate a unique identifier for each function call.
- **config.constants**: Imports the `logger` for logging purposes.

Class Definitions
-----------------
**FunctionCallStack**: A class to manage and track the call stack of functions.

    - **__init__(self)**:
      Initializes an empty stack to keep track of function calls.

    - **track_function(self)**:
      A context manager that tracks the entry and exit of a function. It pushes the function name along with 
      a unique identifier onto the stack when the function is called and pops it off when the function exits.

    - **get_stack(self)**:
      Returns the current call stack as a list of strings.

    - **print_stack(self)**:
      Logs the current call stack using the configured logger.

Usage Example:

    from your_module import FunctionCallStack  # Replace 'your_module' with the actual module name
    
    call_stack = FunctionCallStack()

    def example_function():
        with call_stack.track_function():
            # Function logic here
            pass
    
    example_function()
    call_stack.print_stack()
"""

import logging
from contextlib import contextmanager
import inspect
import uuid
from config.constants import logger

logger = logging.getLogger(__name__)

class FunctionCallStack:
    """
    A class to manage and track the call stack of functions, especially useful 
    for debugging and logging purposes.

    Attributes
    ----------
    stack : list
        A list that maintains the current stack of function calls.

    Methods
    -------
    track_function():
        Context manager that tracks the entry and exit of a function in the call stack.
        
    get_stack():
        Returns the current stack of function calls.
        
    print_stack():
        Logs the current stack of function calls.
    """
    
    def __init__(self):
        """
        Initializes an empty call stack.
        """
        self.stack = []

    @contextmanager
    def track_function(self):
        """
        Context manager for tracking the execution of a function. It captures the 
        name of the function that invokes this context manager, assigns it a unique 
        identifier, and adds it to the call stack. Once the function finishes 
        execution, it is removed from the stack.

        Yields
        ------
        None
            The block within the `with` statement is executed between the 
            `yield` and the removal of the function from the stack.

        Usage example:

            with function_call_stack.track_function():
                # Function logic here
                pass
        """
        # Get the name of the function that called this context manager
        frame = inspect.currentframe().f_back
        function_name = frame.f_code.co_name
        
        # Generate a unique identifier for this specific function call
        unique_id = str(uuid.uuid4())
        entry = f"{function_name} ({unique_id})"
        
        # Push the function call onto the stack
        self.stack.append(entry)
        try:
            yield  # Execution of the block inside `with` happens here
        finally:
            # Pop the function call off the stack
            self.stack.pop()

    def get_stack(self):
        """
        Returns the current call stack.

        Returns
        -------
        list
            A list of strings representing the current stack of function calls.
        """
        return self.stack

    def print_stack(self):
        """
        Logs the current stack of function calls using the configured logger.

        Logs
        ----
        Logs the function calls in the current stack at the INFO level.
        """
        for func in self.stack:
            logger.info(func)