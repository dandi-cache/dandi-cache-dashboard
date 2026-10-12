# DANDI Cache (Dashboard)

A quick reference for the current state of all cache repositories.

Download the table from [`dashboard.tsv`](https://raw.githubusercontent.com/dandi-cache/dandi-cache-dashboard/dashboard/dashboard.tsv).

![DANDI caches](https://raw.githubusercontent.com/dandi-cache/dandi-cache-dashboard/dashboard/dashboard.svg)

## How the caches feed each other

Each arrow points from a cache's sourcedata to the cache built from it.

```mermaid
flowchart LR
    archive[("DANDI archive")]
    content_id_to_dandiset_paths["content-id-to-dandiset-paths"]
    content_id_to_nwb_file["content-id-to-nwb-file"]
    content_id_to_usage_dandiset_path["content-id-to-usage-dandiset-path"]
    content_id_to_valid_nwb_file["content-id-to-valid-nwb-file"]
    dandiset_id_to_number_of_assets["dandiset-id-to-number-of-assets"]
    dandiset_id_to_title["dandiset-id-to-title"]
    dandiset_id_to_total_size["dandiset-id-to-total-size"]
    qualifying_aind_content_ids["qualifying-aind-content-ids"]
    qualifying_lfp_content_ids["qualifying-lfp-content-ids"]
    usage_dandiset_path_to_asset_size["usage-dandiset-path-to-asset-size"]
    valid_nwb_file_to_array_sizes["valid-nwb-file-to-array-sizes"]
    valid_nwb_file_to_byte_weighted_structure["valid-nwb-file-to-byte-weighted-structure"]
    valid_nwb_file_to_chunk_stats["valid-nwb-file-to-chunk-stats"]
    valid_nwb_file_to_cophenetic_index["valid-nwb-file-to-cophenetic-index"]
    valid_nwb_file_to_number_of_datasets["valid-nwb-file-to-number-of-datasets"]
    valid_nwb_file_to_number_of_groups["valid-nwb-file-to-number-of-groups"]
    valid_nwb_file_to_out_degrees["valid-nwb-file-to-out-degrees"]
    valid_nwb_file_to_sackin_index["valid-nwb-file-to-sackin-index"]
    archive --> content_id_to_dandiset_paths
    content_id_to_usage_dandiset_path --> content_id_to_nwb_file
    content_id_to_dandiset_paths --> content_id_to_usage_dandiset_path
    content_id_to_nwb_file --> content_id_to_valid_nwb_file
    archive --> dandiset_id_to_number_of_assets
    archive --> dandiset_id_to_title
    content_id_to_usage_dandiset_path --> dandiset_id_to_total_size
    usage_dandiset_path_to_asset_size --> dandiset_id_to_total_size
    qualifying_lfp_content_ids --> qualifying_aind_content_ids
    content_id_to_usage_dandiset_path --> qualifying_aind_content_ids
    content_id_to_valid_nwb_file --> qualifying_aind_content_ids
    content_id_to_valid_nwb_file --> qualifying_lfp_content_ids
    content_id_to_nwb_file --> qualifying_lfp_content_ids
    content_id_to_usage_dandiset_path --> usage_dandiset_path_to_asset_size
    content_id_to_valid_nwb_file --> valid_nwb_file_to_array_sizes
    valid_nwb_file_to_array_sizes --> valid_nwb_file_to_byte_weighted_structure
    content_id_to_valid_nwb_file --> valid_nwb_file_to_chunk_stats
    content_id_to_valid_nwb_file --> valid_nwb_file_to_cophenetic_index
    content_id_to_valid_nwb_file --> valid_nwb_file_to_number_of_datasets
    content_id_to_valid_nwb_file --> valid_nwb_file_to_number_of_groups
    content_id_to_valid_nwb_file --> valid_nwb_file_to_out_degrees
    content_id_to_valid_nwb_file --> valid_nwb_file_to_sackin_index
```
