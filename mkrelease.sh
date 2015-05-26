#!/bin/bash

VERSION="$1"

die()
{
    echo "$@" >&2
    exit 1
}

[ -n "$VERSION" ] || die "Usage: $0 <version>."

echo ==== Updating source code version numbers to ${VERSION}... ====

sed -i s/VERSION=\"[0-9\\.]\\+\\\(-git\\\)\\?\"/VERSION=\"${VERSION}\"/ flent/build_info.py  || die error
sed -i -e "s/Flent v[0-9\\.]\\+\(-git\)\?/Flent v${VERSION}/" -e "1c .TH FLENT \"1\" \"$(date +"%B %Y")\" \"Flent v${VERSION}.\" \"User Commands\"" man/flent.1  || die error
man -l -Hcat man/flent.1 > man/flent.1.html || die error

if [[ ! "$VERSION" =~ -git$ ]]; then

    echo ==== Updating Debian changelog and Arch PKGBUILD version... ====
    sed -i -e "s/pkgver=.*/pkgver=${VERSION}/" -e "s/sha1sums=([^)]\\+)/sha1sums=()/" packaging/archlinux/PKGBUILD  || die error
    tmpfile=$(mktemp)
    cat >$tmpfile <<EOF
flent (${VERSION}-1) precise; urgency=low

  * Bump to release ${VERSION}.

 -- Toke Høiland-Jørgensen <toke@toke.dk>  $(date +"%a, %d %b %Y %H:%M:%S %z")

EOF

    cat packaging/debian/changelog >> $tmpfile  || die error
    mv $tmpfile packaging/debian/changelog || die error

    echo ==== Creating and signing release tarball... ====
    python setup.py sdist bdist_wheel  || die error
    gpg --detach-sign --armor dist/flent-${VERSION}.tar.gz  || die error
    gpg --detach-sign --armor dist/flent-${VERSION}-py2.py3-none-any.whl  || die error

    echo ==== Updating Arch PKGBUILD sha1sum... ====
    SHA1=$(sha1sum dist/flent-${VERSION}.tar.gz | awk '{print $1}')
    sed -i -e "s/sha1sums=([^)]*)/sha1sums=('${SHA1}')/" packaging/archlinux/PKGBUILD  || die error

fi

echo ==== Staging changed files ====
git add flent/build_info.py man/flent.1{,.html} packaging/debian/changelog packaging/archlinux/PKGBUILD || die error

echo ==== Done. Review changes and commit \(and tag\). ====
[[ ! "$VERSION" =~ -git$ ]] && echo ==== Upload with \`twine upload dist/flent-${VERSION}*\`. ====
