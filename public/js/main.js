    window.addEventListener('pywebviewready', function () {
        window.pywebview.api.do_something().then(() => {
            console.log('API ready & aufgerufen');
        });

    	document.body.style.cursor = 'none';

    });
