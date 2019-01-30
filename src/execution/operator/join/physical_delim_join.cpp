#include "execution/operator/join/physical_delim_join.hpp"
#include "execution/operator/scan/physical_chunk_scan.hpp"
#include "common/vector_operations/vector_operations.hpp"

using namespace duckdb;
using namespace std;

PhysicalDelimJoin::PhysicalDelimJoin(LogicalOperator &op, unique_ptr<PhysicalOperator> original_join, vector<PhysicalOperator*> delim_scans)
    : PhysicalOperator(PhysicalOperatorType::DELIM_JOIN, op.types), join(move(original_join)) {
	assert(delim_scans.size() > 0);
	assert(join->children.size() == 2);
	// for any duplicate eliminated scans in the RHS, point them to the duplicate eliminated chunk that we create here
	for(auto op : delim_scans) {
		assert(op->type == PhysicalOperatorType::CHUNK_SCAN);
		auto scan = (PhysicalChunkScan*) op;
		scan->collection = &delim_data;
	}
	// now for the original join
	// we take its left child, this is the side that we will duplicate eliminate
	children.push_back(move(join->children[0]));
	// we replace it with a PhysicalChunkCollectionScan, that scans the ChunkCollection that we keep cached
	auto cached_chunk_scan = make_unique<PhysicalChunkScan>(children[0]->GetTypes());
	cached_chunk_scan->collection = &lhs_data;
	join->children[0] = move(cached_chunk_scan);
}

void PhysicalDelimJoin::_GetChunk(ClientContext &context, DataChunk &chunk, PhysicalOperatorState *state_) {
	auto state = reinterpret_cast<PhysicalDelimJoinState *>(state_);
	assert(distinct);
	if (!state->join_state) {
		// first run: fully materialize the LHS
		ChunkCollection &big_data = lhs_data;
		do {
			children[0]->GetChunk(context, state->child_chunk, state->child_state.get());
			big_data.Append(state->child_chunk);
		} while (state->child_chunk.size() != 0);
		// now create the duplicate eliminated chunk by pulling from the DISTINCT aggregate
		DataChunk delim_chunk;
		distinct->InitializeChunk(delim_chunk);
		auto distinct_state = distinct->GetOperatorState(nullptr);
		do {
			delim_chunk.Reset();
			distinct->_GetChunk(context, delim_chunk, distinct_state.get());
			delim_data.Append(delim_chunk);
		} while(delim_chunk.size() != 0);
		// create the state of the underlying join
		state->join_state = join->GetOperatorState(nullptr);
	}
	// now pull from the RHS from the underlying join
	join->GetChunk(context, chunk, state->join_state.get());
}

unique_ptr<PhysicalOperatorState> PhysicalDelimJoin::GetOperatorState(ExpressionExecutor *parent_executor) {
	return make_unique<PhysicalDelimJoinState>(children[0].get(), parent_executor);
}

string PhysicalDelimJoin::ExtraRenderInformation() {
	return join->ExtraRenderInformation();
}
