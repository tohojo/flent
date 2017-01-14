#!/bin/bash

VERSION="$1"

die()
{
    echo "$@" >&2
    exit 1
}

[ -n "$VERSION" ] || die "Usage: $0 <version>."

echo ==== Updating source code version numbers to ${VERSION}... ====

sed -i s/VERSION\ =\ \"[0-9\\.]\\+\\\(-git\\\)\\?\"/VERSION\ =\ \"${VERSION}\"/ flent/build_info.py  || die error
sed -i -e "s/version = '[0-9\\.]\\+\\(-git\\)\\?'/version = '${VERSION}'/" doc/conf.py  || die error
make man || die error

if [[ ! "$VERSION" =~ -git$ ]]; then

    echo ==== Updating Arch PKGBUILD version... ====
    sed -i -e "s/pkgver=.*/pkgver=${VERSION}/" packaging/archlinux/PKGBUILD  || die error

    echo ==== Creating and signing release tarball... ====
    python setup.py sdist bdist_wheel  || die error
    gpg --detach-sign --armor dist/flent-${VERSION}.tar.gz  || die error
    gpg --detach-sign --armor dist/flent-${VERSION}-py2.py3-none-any.whl  || die error

    echo ==== Updating Arch PKGBUILD sha256sum... ====
    SHA=$(sha256sum dist/flent-${VERSION}.tar.gz | awk '{print $1}')
    sed -i -e "s/sha256sums=('[a-z0-9]\+'/sha256sums=('${SHA}'/" packaging/archlinux/PKGBUILD  || die error

fi

echo ==== Staging changed files ====
git add flent/build_info.py man/flent.1 doc/conf.py packaging/archlinux/PKGBUILD || die error

echo ==== Done. Review changes and commit \(and tag\). ====
[[ ! "$VERSION" =~ -git$ ]] && echo ==== Upload with \`twine upload dist/flent-${VERSION}*\`. ====
