#!/bin/bash

# Release script for mail time!
# This script helps create and push release tags

if [ -z "$1" ]; then
    echo "Usage: ./release.sh <version>"
    echo "Example: ./release.sh v1.0.0"
    echo ""
    echo "This will:"
    echo "1. Create a git tag"
    echo "2. Push the tag to trigger GitHub Actions build"
    echo "3. Automatically create a release with Windows/Linux builds"
    exit 1
fi

VERSION=$1

# Validate version format
if [[ ! $VERSION =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "❌ Invalid version format. Use: vX.Y.Z (e.g., v1.0.0)"
    exit 1
fi

echo "🚀 Creating release $VERSION..."

# Check if tag already exists
if git tag -l | grep -q "^$VERSION$"; then
    echo "❌ Tag $VERSION already exists!"
    exit 1
fi

# Check if we're on a clean working directory
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Working directory is not clean. Commit your changes first."
    git status --short
    exit 1
fi

# Create and push tag
echo "📝 Creating tag $VERSION..."
git tag -a "$VERSION" -m "Release $VERSION"

echo "⬆️ Pushing tag to GitHub..."
git push origin "$VERSION"

echo ""
echo "✅ Release tag created and pushed!"
echo ""
echo "🔄 GitHub Actions will now:"
echo "   1. Build Windows executable (mailtime.exe)"
echo "   2. Build Linux executable (mailtime)"
echo "   3. Create release with zip/tar.gz files"
echo ""
echo "🌐 Check the progress at:"
echo "   https://github.com/$(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^.]*\).*/\1/')/actions"
echo ""
echo "📦 Release will be available at:"
echo "   https://github.com/$(git config --get remote.origin.url | sed 's/.*github.com[:/]\([^.]*\).*/\1/')/releases"