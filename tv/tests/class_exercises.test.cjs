const assert = require('node:assert/strict');
const {test} = require('node:test');
const {formatExercise} = require('../../8-week-app/static/class_exercises.js');

test('formats reps, scaled calories and distances without changing prescriptions', () => {
  assert.equal(formatExercise({name:'Wall Balls', amount:'20', unit:'reps'}), '20 Wall Balls');
  assert.equal(formatExercise({name:'Row', amount:'12/16', unit:'cal'}), '12/16 cal Row');
  assert.equal(formatExercise({name:'Ski', amount:'1200/1000', unit:'m'}), '1200/1000 m Ski');
  assert.equal(formatExercise({name:'Run', amount:'1.2', unit:'km'}), '1.2 km Run');
});

test('formats minutes and seconds and preserves custom movement instructions', () => {
  assert.equal(formatExercise({name:'Row', unit:'time', minutes:'2', seconds:'20'}),
    'Row - 2 min 20 sec');
  assert.equal(formatExercise({name:'Ski', unit:'time', minutes:'0', seconds:'40'}),
    'Ski - 40 sec');
  assert.equal(formatExercise({name:'Assault Bike', unit:'time', minutes:'3', seconds:''}),
    'Assault Bike - 3 min');
  assert.equal(formatExercise({name:'Custom movement', amount:'10', unit:'reps',
    notes:'synchro / DB 15/22.5 kg'}), '10 Custom movement - synchro / DB 15/22.5 kg');
});

test('rejects missing movements, invalid targets and invalid time fields', () => {
  for (const amount of ['', '0', '-1', '12/0', 'NaN', '12/16/20', 'ten']) {
    assert.throws(() => formatExercise({name:'Row', amount, unit:'cal'}), /target/i);
  }
  assert.throws(() => formatExercise({name:' ', amount:'10', unit:'reps'}), /exercise/i);
  assert.throws(() => formatExercise({name:'Row', amount:'10', unit:'unknown'}), /unit/i);
  assert.throws(() => formatExercise({name:'Row', unit:'time', minutes:'0', seconds:'0'}), /time/i);
  assert.throws(() => formatExercise({name:'Row', unit:'time', minutes:'1', seconds:'60'}), /seconds/i);
  assert.throws(() => formatExercise({name:'Row', unit:'time', minutes:'1.5', seconds:'0'}), /minutes/i);
});
