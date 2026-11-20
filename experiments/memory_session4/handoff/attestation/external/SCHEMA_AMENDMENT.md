# Public schema mapping fixed before outcomes

Initial complete S3 census found the standard nested trajectory location `trajs/{issue}/{issue}.traj.json`. The original strict direct-path parser returned zero eligible pairs. No trace or patch content had been read at this point.

Accept both direct and nested paths, requiring the nested directory identifier to equal the trajectory basename identifier. Ambiguous duplicate identifiers fail the inventory. Keep the same predeclared salt and sample size. Saved v1 parser, selection and lock preserve the initial attempt. Reuse the pinned full listings to select all eligible folders before downloading content. Model extraction additionally preserves a SHA256 of canonical model configuration, its schema keys and a limited safe parameter projection.
