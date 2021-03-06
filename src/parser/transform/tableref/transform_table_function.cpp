#include "duckdb/common/exception.hpp"
#include "duckdb/parser/tableref/table_function_ref.hpp"
#include "duckdb/parser/transformer.hpp"

namespace duckdb {
using namespace std;
using namespace duckdb_libpgquery;

unique_ptr<TableRef> Transformer::TransformRangeFunction(PGRangeFunction *root) {
	if (root->lateral) {
		throw NotImplementedException("LATERAL not implemented");
	}
	if (root->ordinality) {
		throw NotImplementedException("WITH ORDINALITY not implemented");
	}
	if (root->is_rowsfrom) {
		throw NotImplementedException("ROWS FROM() not implemented");
	}
	if (root->functions->length != 1) {
		throw NotImplementedException("Need exactly one function");
	}
	auto function_sublist = (PGList *)root->functions->head->data.ptr_value;
	assert(function_sublist->length == 2);
	auto call_tree = (PGNode *)function_sublist->head->data.ptr_value;
	auto coldef = function_sublist->head->next->data.ptr_value;

	assert(call_tree->type == T_PGFuncCall);
	if (coldef) {
		throw NotImplementedException("Explicit column definition not supported yet");
	}
	auto func_call = (PGFuncCall *)call_tree;
	// transform the function call
	auto result = make_unique<TableFunctionRef>();
	result->function = TransformFuncCall(func_call);
	result->alias = TransformAlias(root->alias, result->column_name_alias);
	result->query_location = func_call->location;
	return move(result);
}

} // namespace duckdb
