#define STORE_BLOCK_CACHE
#define STORE_BLOCK_SINGLE_UNPACK
#include "store_column_blocks.hpp"

int main() {
    CB_CHECK(cuBool_Initialize(CUBOOL_HINT_NO));
    {
        auto identity = store_blocks::make_matrix(3, 3);
        auto first = store_blocks::make_matrix(3, 3);
        auto second = store_blocks::make_matrix(3, 3);
        for (cuBool_Index i = 0; i < 3; ++i)
            CB_CHECK(cuBool_Matrix_SetElement(identity.get(), i, i));
        CB_CHECK(cuBool_Matrix_SetElement(first.get(), 0, 2));
        CB_CHECK(cuBool_Matrix_SetElement(second.get(), 2, 1));
        const std::string a = "Al_store_i_1", b = "Al_store_i_2";
        std::vector<store_blocks::Operand> rights{{&a, first.get()}, {&b, second.get()}};
        store_blocks::PackageCache cache;
        for (int pass = 0; pass < 3; ++pass) {
            if (pass == 2)
                std::reverse(rights.begin(), rights.end());
            MatrixStore output(3);
            store_blocks::multiply(output, identity.get(), rights, &cache);
            for (const auto& entry : rights) {
                cuBool_Index row = 0, col = 0, count = 1;
                CB_CHECK(cuBool_Matrix_ExtractPairs(output.get(*entry.output), &row, &col, &count));
                const bool is_first = *entry.output == a;
                if (count != 1 || row != (is_first ? 0 : 2) || col != (is_first ? 2 : 1))
                    throw std::runtime_error("Wrong cached block pairs");
            }
        }
        if (cache.hits != 1 || cache.matrices.size() != 2)
            throw std::runtime_error("Incorrect ordered cache key");
    }
    CB_CHECK(cuBool_Finalize());
}
