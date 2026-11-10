"""Current automatic shared-folder GUI regression entry point.
Manual reference import/review controls were retired in 1.8.1.
"""
import runpy
runpy.run_path(str(__import__('pathlib').Path(__file__).with_name('studio_link_gui_test.py')),run_name='__main__')
