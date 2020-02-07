var gType = 'product';

colors = {'product': [[0, '#f0f0f5'], [50, 'white'], [60, 'yellow'], [70, 'orange'], [80, 'red']],
          'other': [[0, '#f0f0f5'], [10, 'white'], [20, 'yellow'], [30, 'orange'], [40, 'red']],
          'total': [[0, '#f0f0f5'], [50, 'white'], [100, 'yellow'], [150, 'orange'], [200, 'red']]}


function toggle(type, id='') {
    if (id != '') {
        let parts = id.split(':');
        pval = parts[1];
        oval = parts[2];
        tval = parts[3];

        val = tval;
        baseval = val;
        switch(type) {
            case 'product':
                if (tval <= 0) val = pval;
                else if (tval >= 20) val = ((pval / tval) * 100).toPrecision(3);
                baseval = val;
                if (val == tval) val = '';
                if (val > 0) val += "%";
                break
            case 'other':
                if (tval <= 0) val = oval;
                else if (tval >= 20) val = ((oval / tval) * 100).toPrecision(3);
                baseval = val;
                if (val == tval) val = '';
                if (val > 0) val += "%";
                break
        }
        document.getElementById(id).innerHTML = val;

        var color = '';
        for (var i=0; i < colors[type].length; i++) {
            v = colors[type][i];
            if (baseval > v[0]) color = v[1];
        }
        document.getElementById(id).style.backgroundColor = color;
    }
};

function refresh(type) {
    switch(type) {
        case 'product':
            document.getElementById('product_fix').checked = 'checked';
            document.getElementById('other_fix').checked = '';
            document.getElementById('total_regressions').checked = '';
            gType = 'product';
            break
        case 'other':
            document.getElementById('product_fix').checked = '';
            document.getElementById('other_fix').checked = 'checked';
            document.getElementById('total_regressions').checked = '';
            gType = 'other';
            break
        case 'total':
            document.getElementById('product_fix').checked = '';
            document.getElementById('other_fix').checked = '';
            document.getElementById('total_regressions').checked = 'checked';
            gType = 'total';
            break
    }
    for (var i=0; i < ids.length; i++) {
        toggle(gType, ids[i])
    }
}