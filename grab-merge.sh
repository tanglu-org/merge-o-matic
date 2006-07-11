#!/bin/sh
# grab a merge

# Uncomment if you have an account on casey
#RSYNC=y

# Uncomment if you know that this deletes all the files in the CWD
#EXPERT=y


set -e

if [ "$EXPERT" != "y" ] && [ -n "$(ls)" ]; then
    echo -n "Sure you want to delete all the files in $(pwd) [yn]? "
    read ANSWER
    [ $ANSWER = y ]
fi

MERGE=$1

if [ "${MERGE#lib}" != "${MERGE}" ]; then
    HASH=${MERGE%${MERGE#????}}
else
    HASH=${MERGE%${MERGE#?}}
fi

if [ "$RSYNC" = "y" ]; then
    rsync --verbose --archive --progress --compress --delete \
	casey.ubuntu.com:/srv/patches.ubuntu.com/merges/$HASH/$MERGE/ .
else
    rm -rf  *
    wget -q http://merges.ubuntu.com/$HASH/$MERGE/REPORT

    for NAME in $(sed -n -e "/^    /p" REPORT); do
	echo "Getting $NAME..."
	[ -f $NAME ] || wget -q http://merges.ubuntu.com/$HASH/$MERGE/$NAME
    done
fi
echo

if grep "^generated: " REPORT >/dev/null; then
    VERSION=$(sed -n -e "/^generated:/s/^generated: *//p" REPORT)
    dpkg-source -x ${MERGE}_${VERSION#*:}.dsc
    echo
else
    TARBALL=$(sed -n -e "/\.src\.tar\.gz$/p" REPORT)

    echo unpacking $TARBALL
    tar xf $TARBALL
    echo
fi

if grep "^  C" REPORT; then
    echo
fi

echo "#!/bin/sh" > merge-genchanges
echo "exec $(sed -n -e '/^  $ /s/^  $ //p' REPORT) \"\$@\"" \
    >> merge-genchanges
chmod +x merge-genchanges

echo "#!/bin/sh" > merge-buildpackage
echo "exec $(sed -n -e '/^  $ /s/^  $ dpkg-genchanges/dpkg-buildpackage/p' REPORT) \"\$@\"" \
    >> merge-buildpackage
chmod +x merge-buildpackage

echo "Run ../merge-genchanges or ../merge-buildpackage when done"
