echo "travis branch"
echo $TRAVIS_BRANCH
echo "travis PR"
echo $TRAVIS_PULL_REQUEST

if [[ $TRAVIS_BRANCH == 'master' && $TRAVIS_PULL_REQUEST == 'false' ]]; then
    echo "testing if this works"
fi

if [[ $TRAVIS_BRANCH == 'dockerfile' && $TRAVIS_PULL_REQUEST == 'true' ]]; then
    echo "travis branch"
    echo $TRAVIS_BRANCH
    echo "travis PR"
    echo $TRAVIS_PULL_REQUEST
fi
