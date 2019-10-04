import os


def delete_video_thumnail():
	vidoe_extension = '.mp4'
	image_extension = '.png'
	current_folder = os.getcwd()
	# Remove all png file

	for i in os.listdir(current_folder):
		if i.endswith(image_extension) or i.endswith(vidoe_extension):
			os.remove(os.path.join(current_folder, i))


if __name__ == '__main__':
	delete_video_thumnail()