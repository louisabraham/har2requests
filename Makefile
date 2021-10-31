pypi: dist
	twine upload dist/*
	
dist:
	-rm dist/*
	./setup.py sdist bdist_wheel

clean:
	rm -rf *.egg-info build dist

.PHONY: dist
