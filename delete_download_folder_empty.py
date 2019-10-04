import os


def delete_download_folder_empty():
	current_folder = os.getcwd()
	download_folder = os.path.join(current_folder, 'download')
	# Remove all png file

	for i in os.listdir(download_folder):
		current_dir = os.path.join(download_folder, i)
		if os.path.isdir(current_dir) and len(os.listdir(current_dir)) == 0:
			os.rmdir(current_dir)


if __name__ == '__main__':
	delete_download_folder_empty()