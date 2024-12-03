# cheeseman-lab
Cheeseman lab website

To setup Jekyll:

```bash
conda create -n website
conda activate website
conda install -c conda-forge ruby
conda install -c conda-forge compilers
gem install bundler jekyll
jekyll new . --force
```

To launch test:

```bash
bundle exec jekyll serve
```