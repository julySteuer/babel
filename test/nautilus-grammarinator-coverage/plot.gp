# usage: gnuplot -e "nautilus='out/nautilus.csv'; grammarinator='out/grammarinator.csv'; output='out/edges.png'; output_time='out/edges-time.png'" plot.gp
set terminal pngcairo size 1000,500
set output output
set datafile separator ','
set key left top
set grid
set xlabel 'executions'
set ylabel 'edges covered (cumulative)'
set title 'sqlite edge coverage: Nautilus vs Grammarinator (AFL++ greybox)'
plot nautilus       using 1:2 skip 1 with lines lw 2 title 'Nautilus', \
     grammarinator  using 1:2 skip 1 with lines lw 2 title 'Grammarinator + AFL++'

# same data over wall-clock time (the fair axis: the two tools execute at very different rates)
set output output_time
set xlabel 'seconds'
set title 'sqlite edge coverage over time: Nautilus vs Grammarinator (AFL++ greybox)'
plot nautilus       using 3:2 skip 1 with lines lw 2 title 'Nautilus', \
     grammarinator  using 3:2 skip 1 with lines lw 2 title 'Grammarinator + AFL++'
