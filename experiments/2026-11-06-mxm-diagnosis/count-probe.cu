#include <limits>
#include <thrust/host_vector.h>
#include <nsparse/detail/count_nz.cuh>
#include <cstdio>

#define CUDA_OK(call) do { auto e = (call); if (e != cudaSuccess) { fprintf(stderr, "%s\n", cudaGetErrorString(e)); return 2; } } while (0)

int main() {
    using T = unsigned int;
    T *ar, *ac, *br, *bc, *perm, *nz, *cr;
    CUDA_OK(cudaMallocManaged(&ar, 4*sizeof(T)));
    CUDA_OK(cudaMallocManaged(&ac, 4*sizeof(T)));
    CUDA_OK(cudaMallocManaged(&br, 4*sizeof(T)));
    CUDA_OK(cudaMallocManaged(&bc, 4*sizeof(T)));
    CUDA_OK(cudaMallocManaged(&perm, 3*sizeof(T)));
    CUDA_OK(cudaMallocManaged(&nz, 3*sizeof(T)));
    CUDA_OK(cudaMallocManaged(&cr, 4*sizeof(T)));
    T har[] = {0,0,2,4}, hac[] = {0,1,0,2};
    T hbr[] = {0,1,2,4}, hbc[] = {0,1,1,2};
    for (int i=0;i<4;++i) { ar[i]=har[i]; ac[i]=hac[i]; br[i]=hbr[i]; bc[i]=hbc[i]; cr[i]=0; }
    for (int repeat=0; repeat<5; ++repeat) {
        for (int i=0;i<3;++i) { perm[i]=i; nz[i]=999; }
        nsparse::count_nz_pwarp_row<T,4,256,32><<<1,256>>>(
            thrust::device_pointer_cast(cr), thrust::device_pointer_cast(cr),
            thrust::device_pointer_cast(ar), thrust::device_pointer_cast(ac),
            thrust::device_pointer_cast(br), thrust::device_pointer_cast(bc),
            thrust::device_pointer_cast(perm), thrust::device_pointer_cast(nz), 3u);
        CUDA_OK(cudaGetLastError());
        CUDA_OK(cudaDeviceSynchronize());
        printf("[%u,%u,%u]\n",nz[0],nz[1],nz[2]);
    }
    cudaFree(ar); cudaFree(ac); cudaFree(br); cudaFree(bc); cudaFree(perm); cudaFree(nz); cudaFree(cr);
}
