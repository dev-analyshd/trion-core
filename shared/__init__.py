# TRION shared utilities — package marker.
#
# W4-Q vestigial-status note: NOTHING imports `shared` (grep-proven across
# core/, api/, scripts/, tests/, anima-service/, zg/ — the only "shared"
# references are prose and the distinct chains/shared/ directory). The
# package predates the core/ restructure (its utilities moved to core/*);
# Dockerfile, Dockerfile.railway and Dockerfile.render still COPY this
# directory, so it must keep existing as a directory (removing the COPY
# lines is a build-context change deferred to the deploy custodian). It
# carries no code and no behavior — do not add any (put shared Python in
# core/).
