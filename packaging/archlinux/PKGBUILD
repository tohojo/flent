# Maintainer: Toke Høiland-Jørgensen <toke at toke dot dk>

pkgname=netperf-wrapper
pkgver=0.8.1
pkgrel=2
pkgdesc='A wrapper for the `netperf` benchmark utility, used for testing for bufferbloat.'
arch=('any')
url='https://github.com/tohojo/netperf-wrapper'
license=('GPL')
depends=('python' 'netperf')
optdepends=(
    'python-matplotlib: for outputting graphs'
    'python-pyqt4: for the GUI'
)
source=("https://pypi.python.org/packages/source/n/netperf-wrapper/netperf-wrapper-${pkgver}.tar.gz")
sha1sums=('2a872f296ccaef97207366f524a00489c7e1a284')

package() {
  cd "${srcdir}/${pkgname}-${pkgver}"

  python setup.py install --fake-root --root="$pkgdir" --optimize=1
}
