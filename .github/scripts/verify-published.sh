#!/usr/bin/env bash
#
# Confirm PyPI actually SERVES a version we just published, and that the index
# pip resolves against lists it.
#
# WHY THIS EXISTS. `twine`/the publish action returns success and PyPI processes
# the upload asynchronously, so a green publish step is not evidence that
# anything was published. This reads it back.
#
# WHY TWO ENDPOINTS. They fail independently:
#   * /pypi/<pkg>/<version>/json proves the release object exists.
#   * /simple/<pkg>/ is what a resolver reads. A version present in the first
#     but absent from the second does not install, which is the only outcome a
#     consumer cares about.
# The aggregate /pypi/<pkg>/json is deliberately NOT used: it was observed
# serving a stale `info.version` minutes after a successful publish, which is
# exactly the false signal this script exists to avoid.
#
# Usage: verify-published.sh <package> <version>

set -euo pipefail

PKG="${1:?usage: verify-published.sh <package> <version>}"
VERSION="${2:?usage: verify-published.sh <package> <version>}"

# PyPI's CDN has been seen lagging past five minutes. 40 x 15s gives ten, which
# covers the observed lag. A false red on a good release costs more than the
# extra wait, because it teaches everyone to ignore the check.
ATTEMPTS="${ATTEMPTS:-40}"
INTERVAL="${INTERVAL:-15}"

# A unique query string per attempt is the part the CDN cannot ignore: it
# changes the cache key, so every attempt is a genuine miss. Cache-Control
# alone did not get us a fresh document. PyPI ignores the parameter itself.
bust() { printf '%s?nocache=%s-%s' "$1" "$$" "$2"; }

JSON_URL="https://pypi.org/pypi/${PKG}/${VERSION}/json"
SIMPLE_URL="https://pypi.org/simple/${PKG}/"

echo "Verifying ${PKG}==${VERSION} is served, and that the simple index lists it"

for attempt in $(seq 1 "$ATTEMPTS"); do
  # `|| true`: a transient 5xx or DNS blip must not end the loop early. The
  # loop's own exhaustion is the failure signal, not one bad request.
  served="$(curl -fsS -H 'Cache-Control: no-cache' "$(bust "$JSON_URL" "$attempt")" 2>/dev/null \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["info"]["version"])' 2>/dev/null || true)"
  listed="$(curl -fsS -H 'Cache-Control: no-cache' \
      -H 'Accept: application/vnd.pypi.simple.v1+json' "$(bust "$SIMPLE_URL" "$attempt")" 2>/dev/null \
    | python3 -c "import sys,json; print('yes' if '${VERSION}' in json.load(sys.stdin).get('versions',[]) else '')" 2>/dev/null || true)"

  if [ "$served" = "$VERSION" ] && [ "$listed" = "yes" ]; then
    echo "attempt ${attempt}: served, and the simple index lists ${VERSION}"
    {
      echo "### Published \`${PKG}==${VERSION}\`"
      echo
      echo "Verified against the index, not just the publish step."
    } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
    exit 0
  fi

  echo "attempt ${attempt}/${ATTEMPTS}: release=${served:-<absent>} simple-index=${listed:-<absent>}"
  [ "$attempt" -lt "$ATTEMPTS" ] && sleep "$INTERVAL"
done

# Which half failed changes what to do, so say so rather than printing both and
# leaving the reader to work it out.
if [ "$served" = "$VERSION" ]; then
  echo "::error::${PKG}==${VERSION} exists on PyPI, but the simple index still does not list it after ~$((ATTEMPTS * INTERVAL))s. Resolvers read that index, so 'pip install ${PKG}==${VERSION}' would fail. This is a PyPI-side problem, not a bad upload."
else
  echo "::error::the publish step reported success, but after ~$((ATTEMPTS * INTERVAL))s PyPI does not serve ${PKG}==${VERSION} (release=${served:-<absent>}). Nothing was published."
fi
exit 1
