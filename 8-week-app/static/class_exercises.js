(function(root) {
  'use strict';
  var exercises = [
    {name:'Row', unit:'cal'}, {name:'Ski', unit:'m'},
    {name:'Assault Bike', unit:'cal'}, {name:'Bike Erg', unit:'cal'},
    {name:'Run', unit:'m'}, {name:'Burpees', unit:'reps'},
    {name:'Wall Balls', unit:'reps'}, {name:'DB Squats', unit:'reps'},
    {name:'Dual DB Squats', unit:'reps'}, {name:'Thrusters', unit:'reps'},
    {name:'DB Snatches', unit:'reps'}, {name:'Alt DB Snatches', unit:'reps'},
    {name:'Devil Press', unit:'reps'}, {name:'SA Devil Press', unit:'reps'},
    {name:'DB OH Lunges', unit:'reps'}, {name:'Walking Lunges', unit:'m'},
    {name:'Reverse Lunges', unit:'reps'}, {name:'Farmers Carry', unit:'m'},
    {name:'Sled Push', unit:'m'}, {name:'Sled Pull', unit:'m'},
    {name:'Barbell Clean & Press', unit:'reps'}, {name:'Hand Release Press Ups', unit:'reps'},
    {name:'Walk Outs', unit:'reps'}, {name:'Box Jumps', unit:'reps'},
    {name:'Kettlebell Swings', unit:'reps'}, {name:'Rest', unit:'time'}
  ];

  function formatExercise(data) {
    var name = typeof data.name === 'string' ? data.name.trim() : '';
    if (!name || name.length > 80) throw new Error('Choose or type an exercise (up to 80 characters).');
    var notes = typeof data.notes === 'string' ? data.notes.trim() : '';
    if (notes.length > 160) throw new Error('Keep exercise notes to 160 characters.');
    var text;
    if (data.unit === 'time') {
      var mins = String(data.minutes || '').trim(), secs = String(data.seconds || '').trim();
      if (mins && (!/^\d+$/.test(mins) || Number(mins) > 240)) {
        throw new Error('Minutes must be a whole number between 0 and 240.');
      }
      if (secs && (!/^\d+$/.test(secs) || Number(secs) > 59)) {
        throw new Error('Seconds must be a whole number between 0 and 59.');
      }
      if (!Number(mins) && !Number(secs)) throw new Error('Set a time greater than zero.');
      var time = [];
      if (Number(mins)) time.push(Number(mins) + ' min');
      if (Number(secs)) time.push(Number(secs) + ' sec');
      text = name + ' - ' + time.join(' ');
    } else {
      if (['reps', 'cal', 'm', 'km'].indexOf(data.unit) === -1) {
        throw new Error('Choose reps, calories, time or a distance unit.');
      }
      var amount = typeof data.amount === 'string' ? data.amount.trim() : '';
      if (amount.length > 30 || !/^\d+(?:\.\d+)?(?:\/\d+(?:\.\d+)?)?$/.test(amount) ||
          amount.split('/').some(function(value) { return Number(value) <= 0; })) {
        throw new Error('Set a positive target, such as 20, 1.2 or 12/16.');
      }
      text = amount + (data.unit === 'reps' ? '' : ' ' + data.unit) + ' ' + name;
    }
    return text + (notes ? ' - ' + notes : '');
  }

  var api = {exercises:exercises, formatExercise:formatExercise};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ClassExercises = api;
})(typeof window !== 'undefined' ? window : globalThis);
