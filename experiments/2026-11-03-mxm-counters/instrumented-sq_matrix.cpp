/**********************************************************************************/
/* MIT License                                                                    */
/*                                                                                */
/* Copyright (c) 2020, 2021 JetBrains-Research                                    */
/*                                                                                */
/* Permission is hereby granted, free of charge, to any person obtaining a copy   */
/* of this software and associated documentation files (the "Software"), to deal  */
/* in the Software without restriction, including without limitation the rights   */
/* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell      */
/* copies of the Software, and to permit persons to whom the Software is          */
/* furnished to do so, subject to the following conditions:                       */
/*                                                                                */
/* The above copyright notice and this permission notice shall be included in all */
/* copies or substantial portions of the Software.                                */
/*                                                                                */
/* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR     */
/* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,       */
/* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE    */
/* AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER         */
/* LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,  */
/* OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE  */
/* SOFTWARE.                                                                      */
/**********************************************************************************/

#include <cassert>
#include <core/error.hpp>
#include <sequential/sq_ewiseadd.hpp>
#include <sequential/sq_ewisemult.hpp>
#include <sequential/sq_ewisemultinverted.hpp>
#include <sequential/sq_kronecker.hpp>
#include <sequential/sq_matrix.hpp>
#include <sequential/sq_reduce.hpp>
#include <sequential/sq_spgemm.hpp>
#include <sequential/sq_submatrix.hpp>
#include <sequential/sq_transpose.hpp>
#include <utils/data_utils.hpp>


#include <chrono>
#include <cstdio>
#include <cstdint>
namespace {
struct MxmCounters {
    uint64_t calls=0, accumulated=0, empty_product=0, empty_target=0, both=0;
    uint64_t empty_union_ns=0, other_union_ns=0, row_visits=0;
    uint64_t product_nnz=0, target_nnz=0;
    ~MxmCounters() {
        std::fprintf(stderr, "MXM_COUNTERS {\"calls\":%llu,\"accumulated\":%llu,"
            "\"empty_product\":%llu,\"empty_target\":%llu,\"both\":%llu,"
            "\"empty_union_ns\":%llu,\"other_union_ns\":%llu,"
            "\"row_visits\":%llu,\"product_nnz\":%llu,\"target_nnz\":%llu}\n",
            (unsigned long long)calls, (unsigned long long)accumulated,
            (unsigned long long)empty_product, (unsigned long long)empty_target,
            (unsigned long long)both, (unsigned long long)empty_union_ns,
            (unsigned long long)other_union_ns, (unsigned long long)row_visits,
            (unsigned long long)product_nnz, (unsigned long long)target_nnz);
    }
} mxm_counters;
}

namespace cubool {

    SqMatrix::SqMatrix(size_t nrows, size_t ncols) {
        assert(nrows > 0);
        assert(ncols > 0);

        mData.nrows = nrows;
        mData.ncols = ncols;
    }

    void SqMatrix::setElement(index i, index j) {
        RAISE_ERROR(NotImplemented, "This function is not supported for this matrix class");
    }

    void SqMatrix::build(const index* rows, const index* cols, size_t nvals, bool isSorted, bool noDuplicates) {
        auto nrows = mData.nrows;
        auto ncols = mData.ncols;

        mData.rowOffsets.clear();
        mData.colIndices.clear();

        // Call utility to build csr row offsets and column indices and store in mData vectors
        DataUtils::buildFromData(nrows, ncols, rows, cols, nvals, mData.rowOffsets, mData.colIndices, isSorted, noDuplicates);

        mData.nvals = mData.colIndices.size();
    }

    void SqMatrix::extract(index* rows, index* cols, size_t& nvals) {
        assert(nvals >= getNvals());
        nvals = getNvals();

        if (nvals > 0) {
            DataUtils::extractData(getNrows(), getNcols(), rows, cols, nvals, mData.rowOffsets, mData.colIndices);
        }
    }

    void SqMatrix::extractSubMatrix(const MatrixBase& otherBase, index i, index j, index nrows, index ncols,
                                    bool checkTime) {
        auto other = dynamic_cast<const SqMatrix*>(&otherBase);

        CHECK_RAISE_ERROR(other != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");
        CHECK_RAISE_ERROR(other != this, InvalidArgument, "Matrices must differ");

        assert(this->getNrows() == nrows);
        assert(this->getNcols() == ncols);

        this->allocateStorage();
        other->allocateStorage();
        sq_submatrix(other->mData, this->mData, i, j, nrows, ncols);
    }

    void SqMatrix::clone(const MatrixBase& otherBase) {
        auto other = dynamic_cast<const SqMatrix*>(&otherBase);

        CHECK_RAISE_ERROR(other != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");
        CHECK_RAISE_ERROR(other != this, InvalidArgument, "Matrices must differ");

        assert(other->getNrows() == this->getNrows());
        assert(other->getNcols() == this->getNcols());

        this->mData = other->mData;
    }

    void SqMatrix::transpose(const MatrixBase& otherBase, bool checkTime) {
        auto other = dynamic_cast<const SqMatrix*>(&otherBase);

        CHECK_RAISE_ERROR(other != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");

        assert(other->getNcols() == this->getNrows());
        assert(other->getNrows() == this->getNcols());

        CsrData out;
        out.nrows = this->getNrows();
        out.ncols = this->getNcols();

        this->allocateStorage();
        other->allocateStorage();
        sq_transpose(other->mData, out);

        this->mData = std::move(out);
    }

    void SqMatrix::reduce(const MatrixBase& otherBase, bool checkTime) {
        auto other = dynamic_cast<const SqMatrix*>(&otherBase);

        CHECK_RAISE_ERROR(other != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");

        assert(other->getNrows() == this->getNrows());
        assert(1 == this->getNcols());

        CsrData out;
        out.nrows = this->getNrows();
        out.ncols = this->getNcols();

        this->allocateStorage();
        other->allocateStorage();
        sq_reduce(other->mData, out);

        this->mData = std::move(out);
    }

    void SqMatrix::multiply(const MatrixBase& aBase, const MatrixBase& bBase, bool accumulate, bool checkTime) {
        auto a = dynamic_cast<const SqMatrix*>(&aBase);
        auto b = dynamic_cast<const SqMatrix*>(&bBase);

        CHECK_RAISE_ERROR(a != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");
        CHECK_RAISE_ERROR(b != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");

        assert(a->getNcols() == b->getNrows());
        assert(a->getNrows() == this->getNrows());
        assert(b->getNcols() == this->getNcols());

        CsrData out;
        out.nrows = this->getNrows();
        out.ncols = this->getNcols();

        a->allocateStorage();
        b->allocateStorage();
        ++mxm_counters.calls;
        sq_spgemm(a->mData, b->mData, out);

        if (accumulate) {
            CsrData out2;
            out2.nrows = this->getNrows();
            out2.ncols = this->getNcols();

            this->allocateStorage();
            ++mxm_counters.accumulated;
            bool empty_product = out.nvals == 0;
            bool empty_target = this->mData.nvals == 0;
            mxm_counters.empty_product += empty_product;
            mxm_counters.empty_target += empty_target;
            mxm_counters.both += empty_product && empty_target;
            mxm_counters.row_visits += out.nrows;
            mxm_counters.product_nnz += out.nvals;
            mxm_counters.target_nnz += this->mData.nvals;
            auto union_start = std::chrono::steady_clock::now();
            sq_ewiseadd(this->mData, out, out2);
            auto union_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - union_start).count();
            if (empty_product || empty_target) mxm_counters.empty_union_ns += union_ns;
            else mxm_counters.other_union_ns += union_ns;


            std::swap(out2, out);
        }

        this->mData = std::move(out);
    }

    void SqMatrix::kronecker(const MatrixBase& aBase, const MatrixBase& bBase, bool checkTime) {
        auto a = dynamic_cast<const SqMatrix*>(&aBase);
        auto b = dynamic_cast<const SqMatrix*>(&bBase);

        CHECK_RAISE_ERROR(a != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");
        CHECK_RAISE_ERROR(b != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");

        assert(a->getNrows() * b->getNrows() == this->getNrows());
        assert(a->getNcols() * b->getNcols() == this->getNcols());

        CsrData out;
        out.nrows = this->getNrows();
        out.ncols = this->getNcols();

        a->allocateStorage();
        b->allocateStorage();
        sq_kronecker(a->mData, b->mData, out);

        this->mData = std::move(out);
    }

    void SqMatrix::eWiseAdd(const MatrixBase& aBase, const MatrixBase& bBase, bool checkTime) {
        auto a = dynamic_cast<const SqMatrix*>(&aBase);
        auto b = dynamic_cast<const SqMatrix*>(&bBase);

        CHECK_RAISE_ERROR(a != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");
        CHECK_RAISE_ERROR(b != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");

        assert(a->getNrows() == this->getNrows());
        assert(a->getNcols() == this->getNcols());
        assert(a->getNrows() == b->getNrows());
        assert(a->getNcols() == b->getNcols());

        CsrData out;
        out.nrows = this->getNrows();
        out.ncols = this->getNcols();

        a->allocateStorage();
        b->allocateStorage();
        sq_ewiseadd(a->mData, b->mData, out);

        this->mData = std::move(out);
    }

    void SqMatrix::eWiseMult(const MatrixBase& aBase, const MatrixBase& bBase, bool checkTime) {
        auto a = dynamic_cast<const SqMatrix*>(&aBase);
        auto b = dynamic_cast<const SqMatrix*>(&bBase);

        CHECK_RAISE_ERROR(a != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");
        CHECK_RAISE_ERROR(b != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");

        assert(a->getNrows() == this->getNrows());
        assert(a->getNcols() == this->getNcols());
        assert(a->getNrows() == b->getNrows());
        assert(a->getNcols() == b->getNcols());

        CsrData out;
        out.nrows = this->getNrows();
        out.ncols = this->getNcols();

        a->allocateStorage();
        b->allocateStorage();
        sq_ewisemult(a->mData, b->mData, out);

        this->mData = std::move(out);
    }

    void SqMatrix::eWiseMultInverted(const MatrixBase& aBase, const MatrixBase& bBase, bool checkTime) {
        auto a = dynamic_cast<const SqMatrix*>(&aBase);
        auto b = dynamic_cast<const SqMatrix*>(&bBase);

        CHECK_RAISE_ERROR(a != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");
        CHECK_RAISE_ERROR(b != nullptr, InvalidArgument, "Provided matrix does not belongs to sequential matrix class");

        assert(a->getNrows() == this->getNrows());
        assert(a->getNcols() == this->getNcols());
        assert(a->getNrows() == b->getNrows());
        assert(a->getNcols() == b->getNcols());

        CsrData out;
        out.nrows = this->getNrows();
        out.ncols = this->getNcols();

        a->allocateStorage();
        b->allocateStorage();
        sq_ewisemultinverted(a->mData, b->mData, out);

        this->mData = std::move(out);
    }


    index SqMatrix::getNrows() const {
        return mData.nrows;
    }

    index SqMatrix::getNcols() const {
        return mData.ncols;
    }

    index SqMatrix::getNvals() const {
        return mData.nvals;
    }

    void SqMatrix::allocateStorage() const {
        if (mData.rowOffsets.size() != getNrows() + 1) {
            mData.rowOffsets.clear();
            mData.rowOffsets.resize(getNrows() + 1, 0);
        }
    }
}// namespace cubool