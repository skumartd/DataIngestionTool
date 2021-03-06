# tests/runner.py
import unittest

# import your test modules
import TestCsvToCsv
import TestHiveToHive
import TestJdbcToJdbc

# initialize the test suite
loader = unittest.TestLoader()
suite  = unittest.TestSuite()

# add tests to the test suite
suite.addTests(loader.loadTestsFromModule(TestCsvToCsv))
suite.addTests(loader.loadTestsFromModule(TestHiveToHive))
#suite.addTests(loader.loadTestsFromModule(TestJdbcToJdbc))

#TODO to remove/stop derby instance of each module before running the next module.


# initialize a runner, pass it your suite and run it
runner = unittest.TextTestRunner(verbosity=3)
result = runner.run(suite)