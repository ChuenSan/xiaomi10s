/*
 * Host-only simulation of PID1 directory check: stat() + S_ISDIR.
 * GitHub Actions only. Not packed into the ramdisk.
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int is_dir(const char *path)
{
	struct stat st;

	if (stat(path, &st) != 0)
		return 0;
	return S_ISDIR(st.st_mode);
}

int main(void)
{
	char dir[] = "/tmp/usb0-isdir-XXXXXX";
	char file[160];
	char missing[176];
	int fd;

	if (!mkdtemp(dir)) {
		perror("mkdtemp");
		return 1;
	}
	if (snprintf(file, sizeof(file), "%s/f", dir) >= (int)sizeof(file))
		return 1;
	if (snprintf(missing, sizeof(missing), "%s/missing", dir) >= (int)sizeof(missing))
		return 1;
	fd = open(file, O_CREAT | O_WRONLY, 0600);
	if (fd < 0) {
		perror("open");
		return 1;
	}
	close(fd);

	if (!is_dir(dir)) {
		fprintf(stderr, "directory -> false\n");
		return 1;
	}
	if (is_dir(file)) {
		fprintf(stderr, "regular file -> true\n");
		return 1;
	}
	if (is_dir(missing)) {
		fprintf(stderr, "missing -> true\n");
		return 1;
	}
	printf("HOST_ISDIR_TEST PASS directory=true file=false missing=false\n");
	printf("DIRECTORY_CHECK_IMPL=stat\n");
	return 0;
}
