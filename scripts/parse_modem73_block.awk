tolower($0) ~ /^[[:space:]]*\[\[(modem73)\]\]/ { inblock = 1; next }
inblock && /^[[:space:]]*#/         { next }
inblock && /^[[:space:]]*enabled[[:space:]]*=/ {
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
    sub(/^enabled[[:space:]]*=[[:space:]]*/, "", $0)
    print tolower($0)
    exit
}
inblock && /^[[:space:]]*\[\[/ { exit 1 }
