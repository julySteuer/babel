// Standalone sqlite harness. sqlite3.c is built with -fsanitize-coverage=trace-pc-guard;
// this file is not, so the callbacks below are not instrumented themselves.
// Edge hits go to the file $COV_MAP (1 byte per edge, persistent across runs unless deleted);
// the number of edges set so far is printed to stdout on exit.
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <signal.h>
#include <unistd.h>
#include <sqlite3.h>

#define MAP_SIZE (1 << 20)
#ifndef COV_BUILD  // sancov build only; the llvm-cov build uses cov-analysis's driver main
static uint8_t *map;

void __sanitizer_cov_trace_pc_guard_init(uint32_t *start, uint32_t *stop) {
  static uint32_t n;
  if (!map) {
    const char *path = getenv("COV_MAP");
    int fd = path ? open(path, O_RDWR | O_CREAT, 0644) : -1;
    if (fd >= 0 && ftruncate(fd, MAP_SIZE) == 0)
      map = mmap(0, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (!map || map == MAP_FAILED) map = calloc(MAP_SIZE, 1);
  }
  for (uint32_t *g = start; g < stop; g++) *g = n++ % MAP_SIZE;
}

void __sanitizer_cov_trace_pc_guard(uint32_t *guard) { map[*guard] = 1; }

#endif

#ifdef COV_BUILD
int LLVMFuzzerInitialize(int *argc, char ***argv) { return 0; }  // expected by the driver (no weak symbols on macOS)
#endif

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  sqlite3 *db;
  if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 0;
  char *errmsg = NULL;
  char *sql = sqlite3_malloc((int)size + 1);
  if (sql) {
    memcpy(sql, data, size);
    sql[size] = '\0';
    sqlite3_exec(db, sql, NULL, NULL, &errmsg);
    sqlite3_free(errmsg);
    sqlite3_free(sql);
  }
  sqlite3_close(db);
  return 0;
}

#ifndef COV_BUILD
static void report(int sig) {
  size_t edges = 0;
  for (size_t i = 0; i < MAP_SIZE; i++) edges += map[i] != 0;
  printf("%zu\n", edges);
  fflush(stdout);
  if (sig) _exit(128 + sig);
}

int main(int argc, char **argv) {
  FILE *f = argc > 1 ? fopen(argv[1], "rb") : NULL;
  if (!f) return 2;
  static uint8_t buf[1 << 20];
  size_t n = fread(buf, 1, sizeof buf, f);
  fclose(f);
  chdir("/");            // keep ATTACH / VACUUM INTO from writing into the cwd
  signal(SIGALRM, report), signal(SIGSEGV, report), signal(SIGABRT, report), signal(SIGBUS, report);
  alarm(2);              // runaway queries
  sqlite3_soft_heap_limit64(64 << 20);
  LLVMFuzzerTestOneInput(buf, n);
  report(0);
  return 0;
}
#endif
