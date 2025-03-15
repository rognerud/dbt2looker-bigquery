import pytest
import json
import os
from dbt2looker_bigquery.utils import FileHandler, Sql, DotManipulation, CliError


def test_file_read():
    file_handler = FileHandler()
    file_path = "test_file.json"
    with open(file_path, "w") as f:
        json.dump({"test": "data"}, f)
    assert file_handler.read(file_path) == {"test": "data"}
    os.remove(file_path)


def test_file_read_non_json():
    file_handler = FileHandler()
    file_path = "test_file.txt"
    with open(file_path, "w") as f:
        f.write("test data")
    assert file_handler.read(file_path, file_type=None) == "test data"
    os.remove(file_path)


def test_file_write():
    file_handler = FileHandler()
    file_path = "test_file.txt"
    contents = "test data"
    file_handler.write(file_path, contents)
    with open(file_path, "r") as f:
        assert f.read() == contents
    os.remove(file_path)


def test_validate_sql():
    sql = Sql()
    assert sql.validate_sql("${TABLE}.example") is not None
    assert sql.validate_sql("invalid sql") is None


def test_remove_dots():
    dot_manipulation = DotManipulation()
    assert dot_manipulation.remove_dots("test.data") == "test__data"


def test_last_dot_only():
    dot_manipulation = DotManipulation()
    assert dot_manipulation.last_dot_only("test.data") == "test.data"
    assert dot_manipulation.last_dot_only("test.data.dot") == "test__data.dot"
    assert dot_manipulation.last_dot_only("test") == "test"
    assert dot_manipulation.last_dot_only("test.") == "test."
    assert dot_manipulation.last_dot_only("test..") == "test__."


def test_textualize_dots():
    dot_manipulation = DotManipulation()
    assert dot_manipulation.textualize_dots("test.data") == "test data"


def test_file_not_found():
    file_handler = FileHandler()
    file_path = "non_existent_file.json"
    with pytest.raises(CliError):
        file_handler.read(file_path)


def test_file_write_failure():
    file_handler = FileHandler()
    file_path = "/non_writable_file.txt"
    with pytest.raises(CliError):
        file_handler.write(file_path, "test data")
