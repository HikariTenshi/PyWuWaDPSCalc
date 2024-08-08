from contextlib import contextmanager
import inspect
import uuid

class FunctionCallStack:
    def __init__(self):
        self.stack = []

    @contextmanager
    def track_function(self):
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
        return self.stack

    def print_stack(self):
        for func in self.stack:
            print(func)