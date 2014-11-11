#!/bin/bash

VERSION="$1"

die()
{
    echo "$@" >&2
    exit 1
}

[ -n "$VERSION" ] || die "Usage: $0 <version>."

echo ==== Updating source code version numbers to ${VERSION}... ====

sed -i s/VERSION=\"[0-9\\.]\\+\\\(-git\\\)\\?\"/VERSION=\"${VERSION}\"/ netperf_wrapper/build_info.py  || die error
sed -i -e "s/Netperf-wrapper v[0-9\\.]\\+\(-git\)\?/Netperf-wrapper v${VERSION}/" -e "1c .TH NETPERF-WRAPPER \"1\" \"$(date +"%B %Y")\" \"Netperf-wrapper v${VERSION}.\" \"User Commands\"" man/netperf-wrapper.1  || die error

if [[ ! "$VERSION" =~ -git$ ]]; then

    echo ==== Updating Debian changelog and Arch PKGBUILD version... ====
    sed -i -e "s/pkgver=.*/pkgver=${VERSION}/" -e "s/sha1sums=([^)]\\+)/sha1sums=()/" packaging/archlinux/PKGBUILD  || die error
    tmpfile=$(mktemp)
    cat >$tmpfile <<EOF
netperf-wrapper (${VERSION}-1) precise; urgency=low

  * Bump to release ${VERSION}.

 -- Toke Høiland-Jørgensen <toke@toke.dk>  $(date +"%a, %d %b %Y %H:%M:%S %z")

EOF

    cat packaging/debian/changelog >> $tmpfile  || die error
    mv $tmpfile packaging/debian/changelog || die error

    echo ==== Creating and signing release tarball... ====
    python setup.py sdist  || die error
    gpg --detach-sign --armor dist/netperf-wrapper-${VERSION}.tar.gz  || die error

    echo ==== Updating Arch PKGBUILD sha1sum... ====
    SHA1=$(sha1sum dist/netperf-wrapper-${VERSION}.tar.gz | awk '{print $1}')
    sed -i -e "s/sha1sums=([^)]\\+)/sha1sums=('${SHA1}')/" packaging/archlinux/PKGBUILD  || die error

fi

echo ==== Staging changed files ====
git add netperf_wrapper/build_info.py man/netperf-wrapper.1 packaging/debian/changelog packaging/archlinux/PKGBUILD || die error

echo ==== Done. Review changes and commit and tag. ====
echo ==== Upload with \`twine upload dist/netperf-wrapper-${VERSION}.tar.gz*\`. ====
