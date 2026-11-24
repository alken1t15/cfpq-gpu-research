#pragma once

#include "matrix_store.hpp"
#include "common.hpp"

#include <algorithm>
#include <chrono>
#include <limits>
#include <memory>
#include <string_view>
#include <type_traits>
#include <vector>

namespace store_blocks {

#ifdef STORE_BLOCK_TIMING
using Clock = std::chrono::steady_clock;
inline Clock::duration packing{}, product_time{}, unpacking{};
inline unsigned long long batches = 0;
#endif

struct Operand {
    const std::string* output;
    cuBool_Matrix matrix;
};

inline bool matches(std::string_view a, std::string_view b, std::string_view c) {
    constexpr std::string_view prefix = "store_i_";
    constexpr std::string_view output_prefix = "Al_store_i_";
    if (b != "Al" || !c.starts_with(prefix) || !a.starts_with(output_prefix))
        return false;
    const auto index = c.substr(prefix.size());
    return !index.empty() && index.find_first_not_of("0123456789") == index.npos
        && a.substr(output_prefix.size()) == index;
}

inline auto make_matrix(cuBool_Index rows, cuBool_Index cols) {
    cuBool_Matrix matrix = nullptr;
    CB_CHECK(cuBool_Matrix_New(&matrix, rows, cols));
    return std::unique_ptr<std::remove_pointer_t<cuBool_Matrix>, decltype(&cuBool_Matrix_Free)>(
        matrix, &cuBool_Matrix_Free);
}

inline unsigned long long multiply(MatrixStore& output, cuBool_Matrix left,
                                   const std::vector<Operand>& rights) {
    constexpr size_t batch_limit = 16;
    const auto n = output.n();
    const size_t width_limit = std::min(batch_limit,
        static_cast<size_t>(std::numeric_limits<cuBool_Index>::max() / n));
    unsigned long long calls = 0;
    for (size_t begin = 0; begin < rights.size(); begin += width_limit) {
        const size_t width = std::min(width_limit, rights.size() - begin);
        if (width == 1) {
            const auto& entry = rights[begin];
            CB_CHECK(cuBool_MxM(output.get_ensure(*entry.output), left, entry.matrix,
                               CUBOOL_HINT_ACCUMULATE));
            output.invalidate(*entry.output);
            ++calls;
            continue;
        }
#ifdef STORE_BLOCK_TIMING
        auto phase_start = Clock::now();
        ++batches;
#endif
        std::vector<cuBool_Index> rows, cols;
        for (size_t i = 0; i < width; ++i) {
            cuBool_Index count = 0;
            const auto right = rights[begin + i].matrix;
            CB_CHECK(cuBool_Matrix_Nvals(right, &count));
            const size_t offset = rows.size();
            if (count > std::numeric_limits<cuBool_Index>::max() - offset)
                throw std::overflow_error("Too many packed entries");
            rows.resize(offset + count);
            cols.resize(offset + count);
            if (count) {
                CB_CHECK(cuBool_Matrix_ExtractPairs(right, rows.data() + offset,
                                                   cols.data() + offset, &count));
                for (size_t k = offset; k < cols.size(); ++k)
                    cols[k] += static_cast<cuBool_Index>(i * n);
            }
        }
        const auto packed_columns = static_cast<cuBool_Index>(width * n);
        auto packed = make_matrix(n, packed_columns);
        auto product = make_matrix(n, packed_columns);
        CB_CHECK(cuBool_Matrix_Build(packed.get(), rows.data(), cols.data(),
                                    static_cast<cuBool_Index>(rows.size()), CUBOOL_HINT_NO));
#ifdef STORE_BLOCK_TIMING
        auto now = Clock::now();
        packing += now - phase_start;
        phase_start = now;
#endif
        CB_CHECK(cuBool_MxM(product.get(), left, packed.get(), CUBOOL_HINT_NO));
        ++calls;
        cuBool_Index count = 0;
        CB_CHECK(cuBool_Matrix_Nvals(product.get(), &count));
#ifdef STORE_BLOCK_TIMING
        now = Clock::now();
        product_time += now - phase_start;
        phase_start = now;
#endif
        if (!count)
            continue;
#ifdef STORE_BLOCK_SINGLE_UNPACK
        std::vector<cuBool_Index> result_rows(count), result_cols(count);
        CB_CHECK(cuBool_Matrix_ExtractPairs(product.get(), result_rows.data(), result_cols.data(), &count));
        struct SlicePairs {
            std::vector<cuBool_Index> rows, cols;
        };
        std::vector<SlicePairs> slices(width);
        for (cuBool_Index i = 0; i < count; ++i) {
            auto& slice = slices.at(result_cols[i] / n);
            slice.rows.push_back(result_rows[i]);
            slice.cols.push_back(result_cols[i] % n);
        }
#endif
        for (size_t i = 0; i < width; ++i) {
#ifdef STORE_BLOCK_SINGLE_UNPACK
            const auto& values = slices[i];
            if (values.rows.empty())
                continue;
            auto slice = make_matrix(n, n);
            CB_CHECK(cuBool_Matrix_Build(slice.get(), values.rows.data(), values.cols.data(),
                                        static_cast<cuBool_Index>(values.rows.size()), CUBOOL_HINT_NO));
#else
            auto slice = make_matrix(n, n);
            CB_CHECK(cuBool_Matrix_ExtractSubMatrix(slice.get(), product.get(), 0,
                static_cast<cuBool_Index>(i * n), n, n, CUBOOL_HINT_NO));
            cuBool_Index size = 0;
            CB_CHECK(cuBool_Matrix_Nvals(slice.get(), &size));
            if (!size)
                continue;
#endif
            const auto& key = *rights[begin + i].output;
            if (output.is_empty(key)) {
                output.replace(key, slice.release());
            } else {
                auto merged = make_matrix(n, n);
                CB_CHECK(cuBool_Matrix_EWiseAdd(merged.get(), output.get(key), slice.get(),
                                               CUBOOL_HINT_NO));
                output.replace(key, merged.release());
            }
        }
#ifdef STORE_BLOCK_TIMING
        unpacking += Clock::now() - phase_start;
#endif
    }
    return calls;
}

}  // namespace store_blocks
