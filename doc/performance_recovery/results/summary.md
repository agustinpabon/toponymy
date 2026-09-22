median of three independent warm-process medians; within-process repetitions correlated; no statistical superiority claim

OLD precomputed includes centroids but lacks NEW ownership/validation; OLD plotting leaf sizes are one; OLD persistence lacks NEW integrity/materialization work

Only the tested Toponymy distribution is excluded from shared dependency equality. Its observed metadata is retained here; imported source paths, HEADs and Python source hashes identify the tested revisions separately.

Observed Toponymy distribution metadata: old: toponymy 0.5.2; base: toponymy 0.5.2; optimized: toponymy 0.6.0.dev0.

Ratios are OPT/BASE and OPT/OLD; below one means shorter runtime.

| n | Operation | OLD s | #211 s | OPTIMIZED s | vs #211 | vs OLD |
|---:|---|---:|---:|---:|---:|---:|
| 128 | centroids | 0.000007333 | 0.000008625 | 0.000006708 | 0.778 | 0.915 |
| 128 | precomputed | 0.000039791 | 0.000261750 | 0.000101167 | 0.387 | 2.542 |
| 128 | cluster_tree | 0.000010875 | 0.000047250 | 0.000044125 | 0.934 | 4.057 |
| 128 | topic_hierarchy | 0.000023041 | 0.000026375 | 0.000006416 | 0.243 | 0.278 |
| 128 | legacy_read | 0.005280042 | 0.008305708 | 0.007374708 | 0.888 | 1.397 |
| 512 | centroids | 0.000022125 | 0.000025792 | 0.000023333 | 0.905 | 1.055 |
| 512 | precomputed | 0.000105625 | 0.000499333 | 0.000115416 | 0.231 | 1.093 |
| 512 | cluster_tree | 0.000032750 | 0.000074750 | 0.000063958 | 0.856 | 1.953 |
| 512 | topic_hierarchy | 0.000082583 | 0.000091000 | 0.000014500 | 0.159 | 0.176 |
| 512 | legacy_read | 0.005353167 | 0.008669375 | 0.006983625 | 0.806 | 1.305 |
| 2048 | centroids | 0.000086416 | 0.000102916 | 0.000092875 | 0.902 | 1.075 |
| 2048 | precomputed | 0.000464292 | 0.001655000 | 0.000383792 | 0.232 | 0.827 |
| 2048 | cluster_tree | 0.000137542 | 0.000242625 | 0.000234500 | 0.967 | 1.705 |
| 2048 | topic_hierarchy | 0.000314958 | 0.000344333 | 0.000055459 | 0.161 | 0.176 |
| 2048 | legacy_read | 0.007027500 | 0.015891375 | 0.011903667 | 0.749 | 1.694 |
| 2048 | legacy_fixture | 0.270373584 | 0.327527084 | 0.295630500 | 0.903 | 1.093 |
| 8192 | centroids | 0.000356542 | 0.000468750 | 0.000408834 | 0.872 | 1.147 |
| 8192 | precomputed | 0.002332791 | 0.006735334 | 0.001486541 | 0.221 | 0.637 |
| 8192 | cluster_tree | 0.001062500 | 0.001030250 | 0.001018417 | 0.989 | 0.959 |
| 8192 | topic_hierarchy | 0.001315791 | 0.001353209 | 0.000190000 | 0.140 | 0.144 |
| 8192 | legacy_read | 0.017356292 | 0.047845083 | 0.026988375 | 0.564 | 1.555 |
| 32768 | centroids | 0.001484000 | 0.001891750 | 0.001786417 | 0.944 | 1.204 |
| 32768 | precomputed | 0.010271333 | 0.021182291 | 0.006393959 | 0.302 | 0.623 |
| 32768 | cluster_tree | 0.005677792 | 0.005445750 | 0.005285292 | 0.971 | 0.931 |
| 32768 | topic_hierarchy | 0.005703583 | 0.005958834 | 0.000444084 | 0.075 | 0.078 |
| 32768 | legacy_read | 0.055257250 | 0.159723208 | 0.080498500 | 0.504 | 1.457 |
