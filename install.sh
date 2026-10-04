#!/bin/sh
set -e
dir=${1:-$HOME/Projects/personal-skills}
[ -d "$dir/.git" ] || git clone git@github.com:Shedward/personal-skills.git "$dir"
claude plugin marketplace add "$dir"
claude plugin install my@personal-skills
