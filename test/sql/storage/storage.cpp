
#include "catch.hpp"
#include "test_helpers.hpp"

#include "common/file_system.hpp"

using namespace duckdb;
using namespace std;

TEST_CASE("Test simple storage", "[storage]") {
	unique_ptr<DuckDBResult> result;
	auto storage_database = JoinPath(TESTING_DIRECTORY_NAME, "storage_test");

	// make sure the database does not exist
	if (DirectoryExists(storage_database)) {
		RemoveDirectory(storage_database);
	}
	{
		// create a database and insert values
		DuckDB db(storage_database);
		DuckDBConnection con(db);
		REQUIRE_NO_FAIL(con.Query("CREATE TABLE test (a INTEGER, b INTEGER);"));
		REQUIRE_NO_FAIL(
		    con.Query("INSERT INTO test VALUES (11, 22), (13, 22), (12, 21)"));
	}
	// reload the database from disk
	{
		DuckDB db(storage_database);
		DuckDBConnection con(db);
		result = con.Query("SELECT * FROM test ORDER BY a");
		REQUIRE(CHECK_COLUMN(result, 0, {11, 12, 13}));
		REQUIRE(CHECK_COLUMN(result, 1, {22, 21, 22}));
	}
}