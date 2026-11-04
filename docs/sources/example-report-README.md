<a name="readme-top"></a>

# cfl-idr-with-gll

A Kotlin implementation of CFL-based approximation methods for interleaved Dyck reachability using the GLL-based algorithm.

## Problem Overview

Interleaved Dyck Reachability is a fundamental problem in static program analysis where path constraints are expressed as the shuffle of two Dyck languages - typically representing context sensitivity (parentheses) and field sensitivity (brackets). While this formulation enables high-precision analyses, the problem is known to be undecidable in general, and thus existing approaches resort to clever overapproximations.

This project implements approximation techniques based on the research paper ["CFL-based methods for approximating interleaved Dyck reachability" (Conrado & Pavlogiannis, 2025)](https://www.researchgate.net/publication/390804794_CFL-based_methods_for_approximating_interleaved_Dyck_reachability), which transforms the undecidable problem into a series of tractable CFL reachability problems.

To evaluate these methods, two implementations with different algorithmic approaches were developed:

- **Kotlin implementation (this repository):** Uses an explicit graph-traversal approach with the GLL-based CFL reachability solver from [UCFS](https://github.com/FormalLanguageConstrainedPathQuerying/UCFS).
- **C implementation ([`cfl-idr-with-la`](https://github.com/RodionovMaxim05/cfl-idr-with-la)):** Uses a linear-algebra-based approach with [the CFL reachability solver from LAGraph](https://github.com/SparseLinearAlgebra/LAGraph/blob/homka122/all_algorithms_benchmark/include/LAGraphX.h#L1117).

### Supported Grammars

| Grammar Type | Description                                                                                                                                                                       | Article designation |
|--------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------|
| `parity`     | Mutual refinement with k=1 parity condition on parentheses/brackets: requires the total count of parentheses/bracket symbols to be even                                           | `PAR`               |
| `parity2`    | Mutual refinement with k=2 parity condition: parentheses/brackets are split into 2 groups, count in each group must be even                                                       | `PAR2`              |
| `parityK`    | Mutual refinement with parameterized k-parity condition: parentheses/brackets are split into k groups                                                                             | `PARk`              |
| `se`         | Extends `PAR2` with a "valid endpoints" (structured equality) condition: parentheses/bracket substrings must start with `(`/`[` and end with `)`/`]`                              | `PAR2E`             |
| `project`    | Extends `PAR` with unlabeled projection: additionally runs reachability on the graph with all labels stripped, catching unreachable pairs where total nesting depth is unbalanced | `PARUnl`            |
| `exclude`    | Extends `PAR` with label erasure: iterates over each bracket label, erases it from the graph, and reruns `PAR` - exposing unreachable pairs that were hidden by that label        | `PARErase`          |
| `all`        | Combines `PAR2E` grammar with both the unlabeled projection phase and the label-erasure phase in the mutual refinement loop                                                       | `COM`               |
| `parityD`    | Same grammar as `PAR`, but run in on-demand mode: mutual refinement is performed independently for each queried node pair, filtering out irrelevant graph parts                   | `PARD`              |
| `on-demand`  | Same grammar as `COM`, but run in on-demand mode: combines all stronger grammars and graph simplifications with per-pair refinement                                               | `COMD`              |

## Architecture

The project is organized into two abstraction layers:

1. Programmatic API

	```kotlin
	// Under-approximation (guaranteed reachable)
	fun <V, L : ILabel> getUnderApprox(
		graph: InputGraph<V, L>,
		valueflow: Boolean = false,
		terminalFormat: ITerminalFormat = DefaultTerminalFormat
	): Set<Path<V>>

	// Over-approximation with mutual refinement  
	fun <V, L : ILabel> getMROverApprox(
		graph: InputGraph<V, L>,
		currGrammar: String,
		currParityK: Int = 1,
		underApprox: Set<Path<V>> = emptySet(),
		valueflow: Boolean = false,
		terminalFormat: ITerminalFormat = DefaultTerminalFormat
	): Set<Path<V>>

	// On-demand refinement for specific queries
	fun <V, L : ILabel> getOnDemandMR(
		graph: InputGraph<V, L>,
		underApprox: Set<Path<V>>,
		overApprox: Set<Path<V>>,
		parityD: Boolean = false,
		valueflow: Boolean = false,
		terminalFormat: ITerminalFormat = DefaultTerminalFormat
	): Set<Path<V>>
	```

	See more **[documentation](https://rodionovmaxim05.github.io/cfl-idr-with-gll/cfl-idr-with-gll/org.cfl_idr_with_gll/index.html)** to learn more about it.

2. Command-Line Interface

	```bash
	java -jar cfl-idr-with-gll-all.jar [options] <input.dot> <grammar>
	```

## Value-Flow Analysis Mode

The library provides a specialized value-flow analysis mode (`-valueflow` flag) optimized for memory value-flow analysis: a valid path must start with `[` (similar to the `store` operation) and end with `]` (similar to the `load` operation) with the same id.

`Recommendation` For manual preprocessing before analysis:

```kotlin
// Remove vertices unreachable from store/load operations
val filteredGraph = inputGraph.removeValueflowUnreachable(terminalFormat)
```

## Quick Start

### Requirements

- JDK 21+ (toolchain targets 21)
- Gradle Wrapper included (`./gradlew`)

### Building from Source

```bash
# Clone the repository
git clone https://github.com/RodionovMaxim05/cfl-idr-with-gll.git
cd cfl-idr-with-gll

# Build the project
./gradlew shadowJar -x test

# Initialize submodules (for tests)
git submodule update --init

# Run tests
./gradlew test
```

## Usage Examples

### CLI

```bash
# Basic analysis with parity grammar
java -jar build/libs/cfl-idr-with-gll-all.jar graph.dot parity

# Analysis with parity k=3 and custom output
java -jar build/libs/cfl-idr-with-gll-all.jar graph.dot parityK 3 -o taint-out

# Quiet mode (disable path recording)
java -jar build/libs/cfl-idr-with-gll-all.jar graph.dot parity -q -o result

# Value-flow analysis with parity grammar
java -jar build/libs/cfl-idr-with-gll-all.jar -valueflow graph.dot parity
```

### API Integration

```kotlin
import org.cfl_idr_with_gll.*

// Load graph from DOT file
val dotText = File("graph.dot").readText()
val graph = DotParser().parseDot(dotText)

// Compute approximations
val underPaths = getUnderApprox(graph)
val overPaths = getMROverApprox(graph, "parityK", parityK = 3, underApprox = underPaths)

// Refine on-demand
val onDemandPaths = getOnDemandMR(graph, underPaths, overPaths)
```

## Benchmark

The following section presents a performance analysis comparing this Kotlin (GLL-based) implementation
against the [reference Go implementation](https://github.com/kobusgiovanna/cfl-idr/tree/main)
(or more precisely, a [version with minor modifications](https://github.com/RodionovMaxim05/cfl-idr/commits/main/)), as well as a [C implementation based on GraphBLAS and LAGraph](https://github.com/RodionovMaxim05/cfl-idr-with-la).
All raw results, charts, and scripts are available in the [`benchmark/`](benchmark/) directory.

---

# Performance Analysis

## System Configuration

- **CPU:**  AMD Ryzen 9 7900X, 12 physical, 24 logical cores;

- **RAM:** 128 Gb, 3600 MHz, DDR5;

- **OS:** Linux Ubuntu 22.04;

- **Timeout:** 2 hours (7200 seconds) per benchmark execution.

## Notation and Conventions

The following conventions are used:

1. **`T/O`** (Time out) - a response was not received within the allotted 7200 seconds (2 hours);
2. **`OOM`** (Out of Memory) - the tool ran out of 128 GiB of RAM;
3. **`SOF`** (Stack Overflow Error) - the tool ran out of 12 MiB of stack space.

## Dataset Characteristics & Evaluated Methods

All graphs were obtained from publicly available sources:

- `taint` - graphs from the [taint analysis for Android](https://dl.acm.org/doi/10.1145/2771783.2771803), taken from [this repository](https://github.com/sdingcn/mutual-refinement/tree/main/exp). This data exactly matches the data analyzed in the underlying paper.
- `taint_additional` - graphs from the same source. They relate to the same area of taint analysis but were not included in the evaluation of the underlying paper; the suffix _additional denotes this distinction.
<!-- - `valueflow` - graphs from [value-flow analysis for LLVM](https://dl.acm.org/doi/10.1145/2892208.2892235), also sourced from the same repository above.
- `graphs_unlimited` - Java program-analysis graphs from [this repository](https://github.com/verbinna22/graphs_unlimited/tree/main). In the source repository, each project includes two files:
  - `<name>.g` - original graph extracted from source code;
  - `<name>_slx.g` - context-reduced variant.  
	Labels were uniformly mapped to Dyck symbols:
   	- Store / Load → Open/Close Brackets
   	- Assign Open / Assign Close → Open/Close Parentheses
   	- Everything else → Normal label -->

Below are the key properties of each graph. $|V|$ and $|E|$ represent the number of nodes and edges, respectively; $n_α$ and $n_β$ represent the number of parenthesis and bracket labels present in the graph.

### taint

| Benchmark    | $\|V\|$ | $\|E\|$ | $n_a$ | $n_b$ |
|--------------|---------|---------|-------|-------|
| backflash    | 544     | 2048    | 455   | 6     |
| batterydoc   | 1 674   | 4 790   | 1 132 | 87    |
| droidkongfu  | 734     | 1 983   | 367   | 39    |
| fakebanker   | 434     | 1 103   | 209   | 25    |
| fakedaum     | 1 144   | 2 603   | 715   | 42    |
| faketaobao   | 222     | 450     | 114   | 10    |
| jollyserv    | 488     | 998     | 236   | 28    |
| loozfon      | 152     | 323     | 78    | 3     |
| roidsec      | 553     | 2 026   | 362   | 13    |
| uranai       | 568     | 1 246   | 357   | 8     |
| zertsecurity | 281     | 710     | 166   | 9     |

### taint_additional

| Benchmark | $\|V\|$ | $\|E\|$ | $n_a$  | $n_b$ |
|-----------|---------|---------|--------|-------|
| phospy    | 4 402   | 15 660  | 2 795  | 118   |
| scipiex   | 1 809   | 5 820   | 844    | 173   |
| simhosy   | 4 253   | 13 768  | 2 894  | 330   |
| skullkey  | 18 862  | 69 599  | 12 316 | 1 340 |

<!-- ### valueflow

| Benchmark | $\|V\|$ | $\|E\|$ | $n_a$  | $n_b$ |
|-----------|---------|---------|--------|-------|
| cactus    | 101 325 | 114 805 | 9 840  | 1     |
| imagick   | 103 594 | 131 707 | 13 751 | 1     |
| leela     | 16 134  | 19 110  | 829    | 1     |
| nab       | 12 727  | 13 605  | 331    | 1     |
| omnetpp   | 171 502 | 184 601 | 7 599  | 1     |
| parest    | 84 355  | 93 493  | 2 354  | 1     |
| perlbench | 125 345 | 160 958 | 14 327 | 1     |
| povray    | 61 802  | 71 892  | 5 844  | 1     |
| x264      | 49 806  | 56 376  | 1 546  | 1     |
| xz        | 9 918   | 10 767  | 684    | 1     |

### graphs_unlimited

| Benchmark                     | $\|V\|$ | $\|E\|$   | $n_a$  | $n_b$ |
|-------------------------------|---------|-----------|--------|-------|
| basic                         | 232     | 477       | 25     | 15    |
| basic_slx                     | 232     | 477       | 0      | 15    |
| collection                    | 167     | 313       | 19     | 10    |
| collection_slx                | 167     | 313       | 0      | 10    |
| com_fasterxml_jackson         | 243 766 | 1 070 735 | 8 149  | 2 870 |
| com_fasterxml_jackson_slx     | 243 766 | 1 070 735 | 0      | 2 870 |
| cornerCases                   | 247     | 531       | 30     | 9     |
| cornerCases_slx               | 247     | 531       | 0      | 9     |
| generalJava                   | 157     | 327       | 19     | 11    |
| generalJava_slx               | 157     | 327       | 0      | 11    |
| org_apache_jackrabbit         | 362 181 | 1 740 661 | 15 323 | 7 714 |
| org_apache_jackrabbit_slx     | 362 181 | 1 740 661 | 0      | 7 714 |
| org_jivesoftware_openfire     | 298 555 | 1 006 577 | 14 159 | 5 270 |
| org_jivesoftware_openfire_slx | 298 555 | 1 006 577 | 0      | 5 270 |
| reactor                       | 26 999  | 84 197    | 1 567  | 414   |
| reactor_slx                   | 26 999  | 84 197    | 0      | 414   | -->

#### Evaluated Methods and Solver Composition

Methods (`DEF`, `PAR`, `PAR2E`, etc.) represent high-level algorithms designed for reachability analysis. Each method performs analysis by invoking an underlying CFL reachability solver one or more times using a set of underlying core grammars (for simplicity, we will call them `default_grammar`, `parity_grammar`, `se_grammar`, etc.) as building blocks until algorithm convergence.

The structural composition of each method, specifying which grammars it executes and its iteration pattern, is defined as follows:

| Method     | Composition                                                              |
|------------|--------------------------------------------------------------------------|
| `DEF`      | 2\*`default_grammar`                                                             |
| `PAR`      | 2\*`parity_grammar`                                                              |
| `PAR2`     | 2\*`parity2_grammar`                                                             |
| `PARUnl`   | 2\*`parity_grammar` + `project_grammar`                                                  |
| `PARErase` | 2\*`parity_grammar`​ + `exclude_grammar` \* $n_b$                                         |
| `PAR2E`    | 2\*`se_grammar`                                                                  |
| `COM`      | 2\*`se_grammar` + `project_grammar` + `exclude_grammar` \* $n_b$                                 |
| `PARD`     | `PAR`, then `DEF` \* $n_{uncertain}$                                 |
| `COMD`     | `COM`, then `DEF` \* $n_{uncertain}$, then `COM` \* $n_{uncertain}'$ |

Here $n_{uncertain} = |R_{over}| − |R_{under}|$ is the number of pairs in the over-approximation not confirmed by the under-approximation after the initial global pass, and $n_{uncertain}' \leq n_{uncertain}$​ is the number of pairs remaining after the default per-pair pass. These quantities depend on the graph and grow with graph size, making `PARD` and especially `COMD` the most expensive methods on large inputs.

## Implementation Comparison: C vs Kotlin vs Go

> [!IMPORTANT]
> **Measurement Conditions for Kotlin Solver**
>
> Performance measurements for the Kotlin implementation on the the `taint` and `taint_additional` datasets were performed on an [optimized version of UCFS](libs/solver-new.jar) - the optimization code is available in [PR](https://github.com/FormalLanguageConstrainedPathQuerying/UCFS/pull/50).
<!-- >
> All other measurements (for the `valueflow` and `graphs_unlimited` sets) were performed on the [original UCFS version](libs/solver-original.jar) without optimizations - the original code is available [here](https://github.com/FormalLanguageConstrainedPathQuerying/UCFS/tree/e9c92ba1a85e95e941d04163cd4b55f50686c1f7). -->

### Methodology and Statistical Reliability

For the `taint` dataset, each benchmark execution was repeated 5 times. The results presented in the charts below are the average values ​​of these measurements.  
The sample standard deviation for all measured execution times does not exceed 10% (only 3 of 264 measurements exceed 7%, and all of these measurements were obtained using the Kotlin implementation, with an average time of less than 0.5 seconds, which can be explained by natural error). This variance is low enough to allow meaningful conclusions, as the performance differences between implementations exceed this statistical limit.

For the `taint_additional` dataset, each benchmark execution was repeated 5 times. The sample standard deviation for all measured execution times does not exceed 2%. This variance is also low enough to draw meaningful conclusions.

95% confidence intervals were also calculated for all average execution times.

**Correctness verification:** For all successfully completed graph–grammar pairs, all implementations produced identical path counts ($R_{under}$, $R_{over}$), confirming semantic equivalence of results.

### Results: `taint` Dataset

The comparison was conducted on the [`taint dataset`](benchmark/external-repos/cfl-idr/src/main/taint/).

#### Implementation Comparison (C vs Kotlin vs Go per Grammar)

The following charts compare the execution times across the Go, Kotlin, and C implementations for different grammars:

|                                                                 |                                                               |
|-----------------------------------------------------------------|---------------------------------------------------------------|
| **Grammar `PAR`:**                                              | **Grammar `PAR2`:**                                           |
| <img alt="PAR" src="benchmark/results/taint/parity_time_comparison.png">       | <img alt="PAR2" src="benchmark/results/taint/parity2_time_comparison.png">   |
| **Grammar `PAR2E`:**                                            | **Grammar `PARUnl`:**                                         |
| <img alt="PAR2E" src="benchmark/results/taint/se_time_comparison.png">         | <img alt="PARUnl" src="benchmark/results/taint/project_time_comparison.png"> |
| **Grammar `PARErase`:**                                         | **Grammar `PARD`:**                                           |
| <img alt="PARErase" src="benchmark/results/taint/exclude_time_comparison.png"> | <img alt="PARD" src="benchmark/results/taint/parityD_time_comparison.png">   |
| **Grammar `COM`:**                                              | **Grammar `COMD`:**                                           |
| <img alt="COM" src="benchmark/results/taint/all_time_comparison.png">          | <img alt="COMD" src="benchmark/results/taint/on-demand_time_comparison.png"> |

#### Baseline Comparison (Kotlin and C vs Go)

Both newly developed implementations significantly outperform the reference Go baseline:

- **C vs Go:** The C implementation outperforms Go across all grammars, achieving an average speedup of 17.8×, with speedups ranging from 8× (`COMD`) to 38× (`PAR2`).
- **Kotlin vs Go:** The Kotlin implementation achieves an average speedup of 12.4× over Go across all grammars, with speedups ranging from 1.4× (`PARUnl`) to 34× (`PAR2`).

#### Algorithmic and Architectural Analysis (Kotlin vs C)

Neither implementation dominates universally. The relative performance of the C (matrix-based) and Kotlin (GLL-based) implementations is driven by the interaction between grammar complexity, iteration patterns, and solver architecture.

##### C Limitation: Grammar Size

The performance of the C implementation is directly determined by the number of rules in the grammar passed to the CFL reachability solver, as the computational complexity of each iteration step scales with grammar size. In the matrix-based solver, matrix multiplication operations are executed for each grammar rule; thus, execution time per iteration accumulates proportionally to the rule count.

The individual grammars used across all methods and their resulting rule counts in the C implementation are as follows:

| Grammar           | Standart number of rules in C implementation |
|-------------------|----------------------------------------------|
| `project_grammar` | 8                                            |
| `default_grammar` | 10                                           |
| `parity_grammar`  | 21                                           |
| `parity2_grammar` | 71                                           |
| `exclude_grammar` | 81                                           |
| `se_grammar`      | 1428                                         |

##### Kotlin Limitation: UCFS Descriptor Equality

The primary performance limitation of the Kotlin implementation stems from inefficient equality comparisons within UCFS. During parse forest construction and traversal, the solver frequently compares complex derivation structures. This issue manifests most severely in grammars producing large intermediate structures (`PARUnl`, multi-pass variants) but affects all grammars on sufficiently large inputs.

##### Where C Leads

C implementation leads in methods characterized by low grammar complexity and computations that naturally reduce to sparse matrix operations:

- **`PAR` & `PAR2`:** The `PAR` (C advantage: 1.8×) and `PAR2` (1.2×) methods benefit directly from the efficiency of the GraphBLAS library.
- **`PARUnl`:** C shows the greatest advantage in `PARUnl` (21×). This method adds the `project_grammar` pass (8 rules). Furthermore, the Kotlin implementation handles the `project_grammar` less efficiently than others due to the large number of descriptors it generates.
- **`COM`:** While the `COM` method (C advantage: 4.1×) is faster overall in C, this advantage is largely driven by measurements using the droidkongfu graph; the combined grammar cost of `se_grammar` + `project_grammar` + `exclude_grammar` remains high regardless.

##### Where Kotlin Leads

Kotlin implementation leads in methods that employ complex grammars, involve multiple traversals of bracket labels, or require pairwise refinement of results:

- **`PARErase` & `PARD`:** For methods like `PARErase` and `PARD`, Kotlin's advantage stems from the fact that extracting edges from path-finding results is a resource-intensive operation for GraphBLAS in C. The `PARErase` method (Kotlin advantage: 1.3×) executes the `parity_grammar` once for each bracket label (a total of $n_b$ times). The `PARD` method (1.5×) executes its grammar independently for each query node pair ($n_{uncertain}$ times).
- **`COMD`:** The `COMD` method (Kotlin advantage: 1.2×) similarly executes its grammars independently for each query node pair. Kotlin handles iterations for each pair more efficiently than C.
- **`PAR2E`:** The `PAR2E` method (Kotlin advantage: 1.3×) uses the `se_grammar` — the most computationally expensive of the individual grammars — where the structural overhead inherent to GraphBLAS matrices outweighs the performance gains.

##### Summary

The overall performance ranking thus depends on method structure: C leads on low-rule, matrix-friendly single-pass methods; Kotlin leads on high-iteration or per-pair methods; Go consistently finishes last.

#### Performance Hierarchy

Beyond absolute speed, the implementations exhibit different performance hierarchies regarding how they handle various
grammar types. The performance hierarchy is calculated based on the sum of execution times for all graphs within each
grammar. The total execution time follows these sequences (from fastest to slowest):

| Implementation    | Runtime Hierarchy (From Fast to Slow)                                      |
|-------------------|----------------------------------------------------------------------------|
| **C (GraphBLAS)** | `PAR` → `PARUnl` → `PAR2` → `PARErase` → `PARD` → `PAR2E` → `COM` → `COMD` |
| **Kotlin (GLL)**  | `PAR` → `PAR2` → `PARErase` → `PARD` → `PAR2E` → `PARUnl` → `COM` → `COMD` |
| **Go (Original)** | `PAR` → `PARUnl` → `PARErase` → `PAR2` → `PARD` → `PAR2E` → `COM` → `COMD` |

#### Accuracy of approximations

<figure style="text-align: center;"> <img alt="taint statistics" src="benchmark/results/taint/statistics_taint.png"/> <figcaption>Approximation spread (R<sub>over</sub> - R<sub>under</sub>) for all graphs and grammars in the <code>taint</code></figcaption></figure>

#### Per-Graph Trade-off Analysis (Time vs. Precision)

The following charts illustrate the relationship between execution time and approximation accuracy (measured as $R_{over}$) for individual graphs:

|                                                                                      |                                                                                  |
|--------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| **Graph `backflash`:**                                                               | **Graph `batterydoc`:**                                                          |
| <img alt="backflash" src="benchmark/results/taint/application/graph_backflash_time_comparison.png">       | <img alt="batterydoc" src="benchmark/results/taint/application/graph_batterydoc_time_comparison.png"> |
| **Graph `droidkongfu`:**                                                             | **Graph `fakebanker`:**                                                          |
| <img alt="droidkongfu" src="benchmark/results/taint/application/graph_droidkongfu_time_comparison.png">   | <img alt="fakebanker" src="benchmark/results/taint/application/graph_fakebanker_time_comparison.png"> |
| **Graph `fakedaum`:**                                                                | **Graph `faketaobao`:**                                                          |
| <img alt="fakedaum" src="benchmark/results/taint/application/graph_fakedaum_time_comparison.png">         | <img alt="faketaobao" src="benchmark/results/taint/application/graph_faketaobao_time_comparison.png"> |
| **Graph `jollyserv`:**                                                               | **Graph `loozfon`:**                                                             |
| <img alt="jollyserv" src="benchmark/results/taint/application/graph_jollyserv_time_comparison.png">       | <img alt="loozfon" src="benchmark/results/taint/application/graph_loozfon_time_comparison.png">       |
| **Graph `roidsec`:**                                                                 | **Graph `uranai`:**                                                              |
| <img alt="roidsec" src="benchmark/results/taint/application/graph_roidsec_time_comparison.png">           | <img alt="uranai" src="benchmark/results/taint/application/graph_uranai_time_comparison.png">         |
| **Graph `zertsecurity`:**                                                            |                                                                                  |
| <img alt="zertsecurity" src="benchmark/results/taint/application/graph_zertsecurity_time_comparison.png"> |                                                                                  |

### Results: `taint_additional` Dataset

The comparison was conducted on the [`taint_additional dataset`](benchmark/taint_additional/), which contains larger graphs.

#### Implementation Comparison (C vs Kotlin vs Go per Grammar)

|                                                                                       |                                                                                     |
|---------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| **Grammar `PAR`:**                                                                    | **Grammar `PAR2`:**                                                                 |
| <img alt="PAR" src="benchmark/results/taint_additional/parity_time_comparison.png">       | <img alt="PAR2" src="benchmark/results/taint_additional/parity2_time_comparison.png">   |
| **Grammar `PAR2E`:**                                                                  | **Grammar `PARUnl`:**                                                               |
| <img alt="PAR2E" src="benchmark/results/taint_additional/se_time_comparison.png">         | <img alt="PARUnl" src="benchmark/results/taint_additional/project_time_comparison.png"> |
| **Grammar `PARErase`:**                                                               | **Grammar `PARD`:**                                                                 |
| <img alt="PARErase" src="benchmark/results/taint_additional/exclude_time_comparison.png"> | <img alt="PARD" src="benchmark/results/taint_additional/parityD_time_comparison.png">   |
| **Grammar `COM`:**                                                                    | **Grammar `COMD`:**                                                                 |
| <img alt="COM" src="benchmark/results/taint_additional/all_time_comparison.png">          | <img alt="COMD" src="benchmark/results/taint_additional/on-demand_time_comparison.png"> |

#### Go Implementation Limits

The Go implementation completed successfully only on 4 benchmarks: 2 benchmarks with the `PAR` method for scipiex and simhosy, where it significantly loses to other implementations (the Kotlin implementation wins by 87× and 81×, while the C implementation wins by 58× and 48×, respectively) and with `PARUnl` on the same graphs, where it significantly loses to the C implementation (the losses are 69× and 56×).

#### C vs Kotlin analysis

On the larger taint_additional dataset, both implementations encounter scalability limits — `OOM` and `T/O` failures become frequent, especially on skullkey and phospy. The grammar-complexity-driven pattern from taint holds and becomes more pronounced:

- **`PARUnl`**: C completes on all three feasible graphs (phospy in 3087s, scipiex in 69s, simhosy in 31s), while Kotlin times out on all of them.
- **`PAR2E` & `COM`**: C completes scipiex and simhosy for `PAR2E` 1.9 and 1.04 times faster, respectively, while simhosy completes for `COM` (Kotlin timeouts).
- **`PAR`**: C is faster on phospy (1.1×), but slower on scipiex (1.5×) and simhosy (1.65×). Although the `parity` grammar is cheap for both implementations, profiling of the C implementation on scipiex and simhosy reveals that, alongside the edge extraction overhead discussed earlier, a notable portion of execution time is spent on thread management, suggesting that the parallelism overhead of GraphBLAS becomes more pronounced on graphs of this size. For phospy, the larger graph size likely means that the computational work per iteration is sufficient to amortise these overheads, which may explain C's slight advantage there.
- **`PAR2`, `PARErase`, `PARD`**: For all three methods, Kotlin outperforms C on graphs where both complete.
- **`COMD`**: Neither implementation completes any graph.

#### Performance Hierarchy (only for successful measurements)

| Implementation    | Runtime Hierarchy (From Fast to Slow)                                      |
|-------------------|----------------------------------------------------------------------------|
| **C (GraphBLAS)** | `PAR` → `PARUnl` → `PAR2` → `PAR2E` → `PARD` → `PARErase` → `COM` → `COMD` |
| **Kotlin (GLL)**  | `PAR` → `PAR2` → `PAR2E` → `PARErase` → `PARD` → `PARUnl`/`COM` → `COMD`   |

#### Accuracy of approximations

<figure style="text-align: center;"> <img alt="taint_additional statistics" src="benchmark/results/taint_additional/statistics_taint_additional.png"/> <figcaption>Approximation spread (R<sub>over</sub> - R<sub>under</sub>) for all graphs and grammars in the <code>taint_additonal</code></figcaption></figure>

#### Per-Graph Trade-off Analysis (Time vs. Precision)

|                                                                                                  |                                                                                                  |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| **Graph `phospy`:**                                                                              | **Graph `scipiex`:**                                                                             |
| <img alt="phospy" src="benchmark/results/taint_additional/application/graph_phospy_time_comparison.png">   | <img alt="scipiex" src="benchmark/results/taint_additional/application/graph_scipiex_time_comparison.png"> |
| **Graph `simhosy`:**                                                                             |                                                                                                  |
| <img alt="simhosy" src="benchmark/results/taint_additional/application/graph_simhosy_time_comparison.png"> |                                                                                                  |

### Summary and Conclusions

1. **C vs Go:** The C implementation outperforms (19.6×) Go across all eight methods on the datasets considered. The advantage is largest for low-rule grammars, where GraphBLAS sparse matrix operations provide the greatest relative benefit over Go.
2. **Kotlin vs Go:** The Kotlin GLL-based implementation provides an average speedup (13.9×) over Go in benchmarks where both implementations succeed.
3. **C vs Kotlin:** Neither implementation dominates universally. C leads on methods with small grammars (`PAR`, `PAR2`, `PARUnl`), with the largest gap on `PARUnl` (21×). Kotlin leads on methods dominated by high per-label (`PARErase`) or per-pair iteration (`PARD`, `COMD`) and in `PAR2E` on small graphs.
4. **Correctness preserved:** Identical approximation results in all implementations confirm the semantic accuracy of the implemented approaches.

<!-- ## Data set analysis

### Value-flow

The comparison was conducted on the [`valueflow dataset`](benchmark/valueflow/).

#### Per-Graph Trade-off Analysis (Time vs. Precision)

|                                                                                  |                                                                                    |
|----------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| **Graph `cactus`:**                                                              | **Graph `leela`:**                                                                 |
| <img alt="cactus" src="benchmark/results/valueflow/application/cactus_time_vs_diff_valueflow.png"> | <img alt="leela" src="benchmark/results/valueflow/application/leela_time_vs_diff_valueflow.png">     |
| **Graph `nab`:**                                                                 | **Graph `omnetpp`:**                                                               |
| <img alt="nab" src="benchmark/results/valueflow/application/nab_time_vs_diff_valueflow.png">       | <img alt="omnetpp" src="benchmark/results/valueflow/application/omnetpp_time_vs_diff_valueflow.png"> |
| **Graph `parest`:**                                                              | **Graph `povray`:**                                                                |
| <img alt="parest" src="benchmark/results/valueflow/application/parest_time_vs_diff_valueflow.png"> | <img alt="povray" src="benchmark/results/valueflow/application/povray_time_vs_diff_valueflow.png">   |
| **Graph `x264`:**                                                                | **Graph `xz`:**                                                                    |
| <img alt="x264" src="benchmark/results/valueflow/application/x264_time_vs_diff_valueflow.png">     | <img alt="xz" src="benchmark/results/valueflow/application/xz_time_vs_diff_valueflow.png">           |

Each benchmark in the `valueflow` dataset was executed 3 times; reported values represent averages and 95% confidence intervals.

All grammars exhibit almost identical runtime behavior. At the same time, the `imagick` and `perlbench` graphs did meet the time-out.

This suggests that in the meaning value-flow mode, all grammars work approximately the same way, regardless of their complexity.

This happens because in value-flow mode, the analysis is limited to only those paths that start with `[` and end with `]`. For these graphs, this significantly narrows the search area (for example, only when preprocessing ([function removeValueflowUnreachable](src/main/kotlin/org/cfl_idr_with_gll/graph/ValueflowExtensions.kt#L24)) the `x264` graph, the number of vertices decreases from **49 806** to **13 044**, and the number of edges from **56 376** to **14 351**). Therefore, the difference between grammars becomes insignificant.

However, the approximation yielded an accurate result (as confirmed by the results of the paper). This means that this test suite is not particularly challenging.

### Graphs Unlimited

The comparison was conducted on the [`graphs_unlimited dataset`](benchmark/graphs_unlimited/).  
The `graphs_unlimited` dataset represents the most demanding benchmarks for Interleaved Dyck Reachability. Due to their scale, measurements were limited to a single run per graph using only the simplest grammar (`PAR`) to establish a feasibility baseline.

<figure style="text-align: center;"> <img alt="graphs_unlimited parity perfomance" src="benchmark/results/graphs_unlimited/parity_comparison_of_times_graphs_unlimited.png"/> <figcaption>Performance of <code>PAR</code> grammar for <code>graphs_unlimited</code></figcaption></figure>

- For all larger graphs in this dataset the basic `PAR` grammar failed to complete due to StackOverflowError (`SOF`), Out of Memory (`OOM`), or Timeout (`T/O`).

#### Stack Overflow in UCFS

Three graphs triggered java.lang.StackOverflowError despite increasing the JVM stack size to 12 MB (12× default):

```bash
Exception in thread "main" java.lang.StackOverflowError
  at org.ucfs.grammar.combinator.regexp.Regexp$DefaultImpls.getAlphabet(Regexp.kt:30)
  at org.ucfs.grammar.combinator.regexp.Alternative.getAlphabet(Alternative.kt:6)
  ...
```

The error occurs due to the recursive traversal of the grammar combinator structure in UCFS during the construction of the rsm (Recursive State Machine) - this is a limitation of the current recursive implementation when processing large grammars.

#### Precision for Successful Subsets

<figure style="text-align: center;"> <img alt="graphs_unlimited statistics" src="benchmark/results/graphs_unlimited/statistics_graphs_unlimited.png"/> <figcaption>R<sub>over</sub> - R<sub>under</sub> for all <code>graphs_unlimited</code> graphs and grammars</figcaption></figure>

For the subset of graphs that did complete (e.g., basic, collection, generalJava), the precision was high.

- In most completed cases like collection_slx and generalJava_slx, the precision gap $|R_{over} - R_{under}|$ was 0, indicating that the approximation reached the exact solution.
- Even in cases with a gap, such as basic or cornerCases, the difference remained constant at 2 across almost all grammar types. -->

## License

Distributed under the [MIT License](https://choosealicense.com/licenses/mit/). See [`LICENSE`](LICENSE) for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>
